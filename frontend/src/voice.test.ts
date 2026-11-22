import assert from 'node:assert/strict'
import { test } from 'node:test'
import { finalText, problemOf, type SpeechEvent } from './voice.ts'

test('speech errors become plain reasons; a blocked microphone is told apart from silence', () => {
  assert.equal(problemOf('not-allowed'), 'blocked')
  assert.equal(problemOf('service-not-allowed'), 'blocked')
  assert.equal(problemOf('no-speech'), 'nothing')
  assert.equal(problemOf('network'), 'failed')
})

const result = (transcript: string, isFinal: boolean) => Object.assign([{ transcript }], { isFinal })

test('a growing phrase is taken once, when final, not each partial (seen in Chrome on 22 November)', () => {
  const heard = [
    { resultIndex: 0, results: [result('Find', false)] },
    { resultIndex: 0, results: [result('Find 6', false)] },
    { resultIndex: 0, results: [result('Find 6 amp', false)] },
    { resultIndex: 0, results: [result('Find 6 amp switch', true)] },
  ] satisfies SpeechEvent[]
  assert.deepEqual(heard.map(finalText).filter(Boolean), ['Find 6 amp switch'])
})

test('a later phrase in the same session adds only the new final result', () => {
  const e: SpeechEvent = { resultIndex: 1, results: [result('find 6 amp switch', true), result('100', true)] }
  assert.equal(finalText(e), '100')
})

test('a number followed by a misheard amp becomes amp; other words are left alone', async () => {
  const { tidy } = await import('./voice.ts')
  assert.equal(tidy('find 6 apps switch'), 'find 6 amp switch') // heard in the owner's test on 22 November
  assert.equal(tidy('Find 16 amps one way'), 'Find 16 amp one way')
  assert.equal(tidy('show my apps'), 'show my apps')
  assert.equal(tidy('find 6 amp which'), 'find 6 amp switch')
  assert.equal(tidy('Quart'), 'quote')
  assert.equal(tidy('Code'), 'quote') // heard for "quote" on its own
  assert.equal(tidy('product code 12'), 'product code 12') // a real word inside a sentence is kept
  assert.equal(tidy('which one is cheaper'), 'which one is cheaper') // which alone is left alone
})

test('the phrase still being heard is shown live but is not final text', async () => {
  const { interimText } = await import('./voice.ts')
  const e: SpeechEvent = { resultIndex: 0, results: [result('raddu', false)] }
  assert.equal(interimText(e), 'raddu')
  assert.equal(finalText(e), '')
})
