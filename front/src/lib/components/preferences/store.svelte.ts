import { getContext, setContext } from "svelte";
import { toast } from "svelte-sonner";
import {
  emptyPreferences,
  type PreferencesApiErrorPayload,
  type PreferencesData
} from "$lib/preferences";
import {
  buildPayload,
  createFormState,
  payloadSnapshot,
  type PreferencesFormState
} from "./types.js";

const parseApiError = (payload: PreferencesApiErrorPayload | PreferencesData, fallback: string) => {
  if ("detail" in payload && payload.detail?.trim()) {
    return payload.detail.trim();
  }
  return fallback;
};

// Общее состояние формы Preferences: живёт на странице, разделы читают его через контекст,
// поэтому переключение раздела не теряет несохранённые изменения.
export class PreferencesStore {
  preferences = $state<PreferencesData | null>(null);
  loadError = $state("");
  saveError = $state("");
  isSaving = $state(false);
  form = $state<PreferencesFormState>(createFormState(emptyPreferences()));
  hasUnsavedChanges = $state(false);
  formRevision = $state(0);
  initialSnapshot = $state(payloadSnapshot(createFormState(emptyPreferences())));

  // Ключ последних применённых данных load(): защищает форму от лишних сбросов,
  // когда эффект перезапускается без реального изменения данных с сервера.
  #loadedKey = "";

  constructor(readInitialData?: () => { preferences: PreferencesData | null; apiError?: string }) {
    // Инициализация из load() до первого рендера — без мигания «не удалось загрузить».
    if (readInitialData) this.applyData(readInitialData());
  }

  currentSnapshot = $derived.by(() => {
    // formRevision заставляет пересчитать снимок после ручных мутаций полей.
    this.formRevision;
    return payloadSnapshot(this.form);
  });

  isDirty = $derived(
    Boolean(this.preferences) &&
      (this.hasUnsavedChanges || this.currentSnapshot !== this.initialSnapshot)
  );

  markDirty = () => {
    this.formRevision++;
    this.hasUnsavedChanges = true;
  };

  applyData = (data: { preferences: PreferencesData | null; apiError?: string }) => {
    const loadedKey = `${JSON.stringify(data.preferences)}|${data.apiError ?? ""}`;
    // Повторный вызов с теми же данными не должен сбрасывать несохранённые правки.
    if (loadedKey === this.#loadedKey) return;
    this.#loadedKey = loadedKey;

    this.preferences = data.preferences ?? null;
    this.loadError = data.apiError ?? "";
    this.saveError = "";

    const nextPreferences = data.preferences ?? emptyPreferences();
    const nextFormState = createFormState(nextPreferences);
    this.form = nextFormState;
    this.hasUnsavedChanges = false;
    this.initialSnapshot = payloadSnapshot(nextFormState);
  };

  resetForm = () => {
    const nextPreferences = this.preferences ?? emptyPreferences();
    this.form = createFormState(nextPreferences);
    this.hasUnsavedChanges = false;
    this.saveError = "";
  };

  save = async () => {
    this.isSaving = true;
    this.saveError = "";

    try {
      const response = await fetch("/api/core/preferences", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(buildPayload(this.form))
      });

      const payload = (await response.json()) as PreferencesData | PreferencesApiErrorPayload;
      if (!response.ok) {
        throw new Error(parseApiError(payload, `HTTP ${response.status}`));
      }

      const savedPreferences = payload as PreferencesData;
      this.preferences = savedPreferences;
      const nextFormState = createFormState(savedPreferences);
      this.form = nextFormState;
      this.hasUnsavedChanges = false;
      this.initialSnapshot = payloadSnapshot(nextFormState);
      toast.success("Preferences сохранены.");
    } catch (error) {
      this.saveError = error instanceof Error ? error.message : "Сохранить настройки не удалось.";
      toast.error(this.saveError);
    } finally {
      this.isSaving = false;
    }
  };
}

const PREFERENCES_STORE_KEY = Symbol("preferences-store");

export const setPreferencesStore = (store: PreferencesStore) => {
  setContext(PREFERENCES_STORE_KEY, store);
};

export const getPreferencesStore = (): PreferencesStore => {
  const store = getContext<PreferencesStore | undefined>(PREFERENCES_STORE_KEY);
  if (!store) {
    throw new Error("PreferencesStore is not available: wrap the markup in the preferences page.");
  }
  return store;
};
