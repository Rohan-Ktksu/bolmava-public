import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileDetails } from './evidence.ts'

test('file details carry the SHA-256 of the bytes and a fallback type, never the file', async () => {
  const d = await fileDetails(new File(['abc'], 'photo.jpg'))
  assert.deepEqual(d, {
    filename: 'photo.jpg',
    content_type: 'application/octet-stream',
    size_bytes: 3,
    sha256: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad', // SHA-256("abc"), FIPS 180-2 test vector
  })
})
