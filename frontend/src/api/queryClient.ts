import { QueryClient } from '@tanstack/react-query'

// The backend already retries transient provider errors; client retries would only multiply
// requests against the weather quota.
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
}
