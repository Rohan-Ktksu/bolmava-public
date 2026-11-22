/**
 * Browser speech-to-text (the Web Speech API), free and without an account. Chrome and Edge send the audio to their
 * vendor's speech service, so the screen says so; the person always reads the text and presses Send themselves.
 */
type Result = ArrayLike<{ transcript: string }> & { isFinal: boolean }
export type SpeechEvent = { resultIndex: number; results: ArrayLike<Result> }
export type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  onresult: ((e: SpeechEvent) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}
type Ctor = new () => Recognition
const ctor = (): Ctor | undefined => {
  const w = window as unknown as { SpeechRecognition?: Ctor; webkitSpeechRecognition?: Ctor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export const speechSupported = () => !!ctor()

/** Why listening ended without text, as an i18n key suffix. */
export type VoiceProblem = 'blocked' | 'nothing' | 'failed'
export const problemOf = (error: string): VoiceProblem =>
  error === 'not-allowed' || error === 'service-not-allowed' ? 'blocked' : error === 'no-speech' ? 'nothing' : 'failed'

/**
 * The finished phrases new in this event. Chrome can report a phrase while it is still growing ("Find", "Find 6", ...)
 * even with interim results off; only final results count, and each only once (from `resultIndex` on).
 */
export function finalText(e: SpeechEvent): string {
  const out: string[] = []
  for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) out.push(e.results[i][0]?.transcript ?? '')
  return out.join(' ').trim()
}

/** The phrase still being heard, for live feedback only; it never goes into the message box. */
export function interimText(e: SpeechEvent): string {
  const out: string[] = []
  for (let i = e.resultIndex; i < e.results.length; i++) if (!e.results[i].isFinal) out.push(e.results[i][0]?.transcript ?? '')
  return out.join(' ').trim()
}

/**
 * Known slips of the browser's general vocabulary in this catalog, all heard in the owner's tests on 22 November:
 * "6 apps switch" for "6 amp switch", "6 amp which" for "6 amp switch", and "quart" or "code" for "quote".
 * "code", "court" and "coat" are real words, so they become "quote" only when spoken on their own.
 */
export const tidy = (text: string) =>
  text
    .replace(/(\d+)\s*(?:apps|aps|abs|amps?)\b/gi, '$1 amp')
    .replace(/(\d+ amp)\s+which\b/gi, '$1 switch')
    .replace(/\b(?:quart|quot)\b/gi, 'quote')
    .replace(/^\s*(?:code|court|coat)\s*$/i, 'quote')

/** Listen in `lang` (te-IN or en-IN) until stopped or the browser gives up. Returns a stop function. */
export function listen(lang: string, on: { text: (t: string) => void; hearing: (t: string) => void; problem: (p: VoiceProblem) => void; end: () => void }) {
  const r = new (ctor()!)()
  r.lang = lang
  r.continuous = true // keep listening through pauses until the person presses Stop listening
  r.interimResults = true // live feedback while Chrome waits for the end of the phrase
  r.maxAlternatives = 1
  r.onresult = (e) => {
    on.hearing(interimText(e))
    const done = finalText(e)
    if (done) on.text(tidy(done))
  }
  r.onerror = (e) => e.error !== 'aborted' && on.problem(problemOf(e.error))
  r.onend = on.end
  r.start()
  return () => r.stop()
}
