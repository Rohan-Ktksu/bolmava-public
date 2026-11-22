/** SHA-256 and details of a chosen file, computed in the browser. Only these details are sent; the file itself is never uploaded (SPEC.md O5). */
export async function fileDetails(file: File) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()))
  const sha256 = Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('')
  return { filename: file.name.slice(0, 200), content_type: (file.type || 'application/octet-stream').slice(0, 100), size_bytes: file.size, sha256 }
}
