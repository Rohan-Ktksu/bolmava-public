import { useEffect, useRef, useState } from 'react'
import { useLang } from './i18n.tsx'
import { listen, speechSupported, type VoiceProblem } from './voice.ts'

/** Speak instead of typing. The words land in the text box; nothing is sent until the person presses Send. */
export function VoiceButton({ onText, label, compact }: { onText: (text: string) => void; label?: string; compact?: boolean }) {
  const { t, lang } = useLang()
  const [listening, setListening] = useState(false)
  const [problem, setProblem] = useState<VoiceProblem | null>(null)
  const [hearing, setHearing] = useState('')
  const stop = useRef<(() => void) | null>(null)
  useEffect(() => () => stop.current?.(), [])
  // compact: a form shows these notes once, not beside every field.
  if (!speechSupported()) return compact ? null : <p className="note">{t('voice.unsupported')}</p>
  // Browsers allow the microphone only on https or localhost; say so instead of a misleading "blocked".
  if (!window.isSecureContext) return compact ? null : <p className="note">{t('voice.insecure')}</p>

  const toggle = () => {
    if (listening) return stop.current?.()
    setProblem(null)
    setListening(true)
    try {
      stop.current = listen(lang === 'te' ? 'te-IN' : 'en-IN', {
        text: (x) => x && onText(x),
        hearing: setHearing,
        problem: setProblem,
        end: () => ((stop.current = null), setListening(false), setHearing('')),
      })
    } catch {
      setListening(false)
      setProblem('failed')
    }
  }
  return (
    <div className="voice">
      <button type="button" className="btn" aria-pressed={listening} aria-label={label && !listening ? label : undefined} onClick={toggle}>
        {t(listening ? 'voice.stop' : 'voice.speak')}
      </button>
      {hearing && <p className="voice-hearing">{t('voice.hearing', { text: hearing })}</p>}
      {!compact && <p className="note">{t('voice.note')}</p>}
      {problem && (
        <p className="field-error" role="alert">
          {t(`voice.${problem}`)}
        </p>
      )}
      <p className="visually-hidden" role="status">
        {listening ? t('voice.listening') : ''}
      </p>
    </div>
  )
}
