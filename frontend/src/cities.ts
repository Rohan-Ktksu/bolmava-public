// The API accepts at most 50 delivery cities of up to 80 characters each (SPEC.md 6.4 ProductCreate).
export const MAX_CITIES = 50
export const MAX_CITY_LENGTH = 80

/** Adds a typed city to the list: trims and collapses spaces, ignores blanks and case-insensitive duplicates. */
export function addCity(list: string[], typed: string): { list: string[]; error?: 'tooLong' | 'tooMany' | 'duplicate' } {
  const city = typed.trim().replace(/\s+/g, ' ')
  if (!city) return { list }
  if (city.length > MAX_CITY_LENGTH) return { list, error: 'tooLong' }
  if (list.some((c) => c.toLowerCase() === city.toLowerCase())) return { list, error: 'duplicate' }
  if (list.length >= MAX_CITIES) return { list, error: 'tooMany' }
  return { list: [...list, city] }
}
