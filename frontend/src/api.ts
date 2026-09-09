export async function requestJson(input: string, init?: RequestInit) {
  const res = await fetch(input, init)
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: `http ${res.status}` }))
    throw new Error(payload?.detail || `http ${res.status}`)
  }
  return res.json()
}
