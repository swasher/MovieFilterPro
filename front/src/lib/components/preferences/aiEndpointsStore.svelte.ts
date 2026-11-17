import { getContext, setContext } from "svelte";
import { listAiEndpoints, type AiEndpoint } from "$lib/aiEndpoints";

// Единый источник endpoints для страницы Preferences: состояние живёт здесь,
// разделы (AI, Kinorium sync, Диагностика) читают его через контекст и не
// держат собственных копий. Синхронизация с load()-данными — applyData().
export class AiEndpointsStore {
  endpoints = $state<AiEndpoint[]>([]);
  error = $state("");
  loading = $state(false);

  selected = $derived(this.endpoints.find((endpoint) => endpoint.is_selected) ?? null);

  // Данные load() читаются лениво через колбэк — как в PreferencesStore,
  // чтобы не фиксировать начальное значение data в состоянии.
  constructor(
    readInitialData?: () => { endpoints: AiEndpoint[]; error: string }
  ) {
    if (readInitialData) this.applyData(readInitialData());
  }

  /** Обновляет состояние данными load(). Вызывается из $effect страницы. */
  applyData(data: { endpoints: AiEndpoint[]; error: string }) {
    this.endpoints = data.endpoints;
    this.error = data.error;
  }

  /** Перечитывает endpoints с сервера. Возвращает false при ошибке. */
  async refresh(): Promise<boolean> {
    this.loading = true;
    try {
      this.endpoints = await listAiEndpoints();
      this.error = "";
      return true;
    } catch (error) {
      this.error = error instanceof Error ? error.message : "Не удалось загрузить AI endpoints.";
      return false;
    } finally {
      this.loading = false;
    }
  }
}

const AI_ENDPOINTS_STORE_KEY = Symbol("ai-endpoints-store");

export const setAiEndpointsStore = (store: AiEndpointsStore) => {
  setContext(AI_ENDPOINTS_STORE_KEY, store);
};

export const getAiEndpointsStore = (): AiEndpointsStore => {
  const store = getContext<AiEndpointsStore | undefined>(AI_ENDPOINTS_STORE_KEY);
  if (!store) {
    throw new Error("AiEndpointsStore is not available: wrap the markup in the preferences page.");
  }
  return store;
};
