import { useEffect, useState } from 'react';
import { llmConnectionService, LlmProviderPreset } from '../services/api';
let providersRequest: Promise<LlmProviderPreset[]> | null = null;
export function useLlmProviders(): LlmProviderPreset[] | null {
  const [providers, setProviders] = useState<LlmProviderPreset[] | null>(null);
  useEffect(() => {
    let active = true;
    providersRequest ??= llmConnectionService.getProviders().catch((err) => {
      providersRequest = null;
      throw err;
    });
    providersRequest
      .then((list) => {
        if (active) setProviders(list);
      })
      .catch(() => {
        if (active) setProviders([]);
      });
    return () => {
      active = false;
    };
  }, []);
  return providers;
}
export const providerLabel = (providers: LlmProviderPreset[] | null, provider: string): string =>
  providers?.find((preset) => preset.provider === provider)?.label || provider;
export default useLlmProviders;
