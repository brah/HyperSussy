import type { QueryClient } from "@tanstack/react-query";

export function invalidateWhalesQueries(
  queryClient: QueryClient
): Promise<unknown[]> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["whales"] }),
    queryClient.invalidateQueries({ queryKey: ["whale-count"] }),
  ]);
}
