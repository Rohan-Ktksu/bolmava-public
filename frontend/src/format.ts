/** Commercial times are shown in India Standard Time whatever the device's timezone (owner convention: Asia/Kolkata). */
export function formatIst(iso: string, lang: string): string {
  const f = new Intl.DateTimeFormat(lang === 'te' ? 'te-IN' : 'en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' })
  return `${f.format(new Date(iso))} IST`
}
