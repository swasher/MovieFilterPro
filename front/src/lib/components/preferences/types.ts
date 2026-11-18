import type { PreferencesData, PreferencesUpdatePayload } from "$lib/preferences";

// Должно совпадать с MIN_SCAN_INTERVAL_MINUTES в core/api.py.
export const MIN_SCAN_INTERVAL_MINUTES = 15;

export type PreferencesFormState = {
  last_scan: string;
  scan_schedule_enabled: boolean;
  scan_interval_minutes: string;
  countries: string;
  genres: string;
  max_year: string;
  min_rating: string;
  low_countries: string;
  low_genres: string;
  low_max_year: string;
  low_min_rating: string;
  plex_address: string;
  plex_token: string;
  cookie_pass: string;
  cookie_uid: string;
  kinozal_domain: string;
  kinozal_mirrors: string[];
  qbt_url: string;
  qbt_api_key: string;
  qbt_skip_cert_verify: boolean;
  torrents_backup_folder: string;
  ignore_title: string;
  tmdb_api_key: string;
  omdb_api_key: string;
  tavily_api_key: string;
  searxng_url: string;
  tmdb_v4_read_access_token: string;
  ai_enabled: boolean;
  kinorium_fast_ai_endpoint_id: string;
  kinorium_deep_ai_endpoint_id: string;
  vault_image_cache_enabled: boolean;
  player_enabled: boolean;
  player_path_map: string;
};

export type PreferencesSectionId =
  | "kinozal"
  | "rules"
  | "qbittorrent"
  | "plex"
  | "images"
  | "player"
  | "tmdb"
  | "omdb"
  | "websearch"
  | "writeback"
  | "local-ai"
  | "kinorium-sync"
  | "taste"
  | "account"
  | "diagnostics";

export type PreferencesSection = {
  id: PreferencesSectionId;
  title: string;
  description: string;
  group: string;
};

// Порядок и группировка пунктов левой навигации Preferences: один пункт — одна настройка/интеграция.
export const PREFERENCES_SECTIONS: PreferencesSection[] = [
  {
    id: "kinozal",
    title: "Kinozal",
    group: "Скан",
    description: "Cookies, зеркала Kinozal, контрольная раздача и автосканирование по расписанию."
  },
  {
    id: "rules",
    title: "Фильтрация",
    group: "Скан",
    description: "Базовые правила фильтрации и low-priority логика для скана."
  },
  {
    id: "qbittorrent",
    title: "qBittorrent",
    group: "Загрузки",
    description:
      "Web API qBittorrent и папка backup для .torrent-файлов. URL должен быть доступен с backend."
  },
  {
    id: "plex",
    title: "Plex",
    group: "Медиа",
    description: "Параметры подключения для Plex-сценариев."
  },
  {
    id: "images",
    title: "Изображения",
    group: "Медиа",
    description: "Кеширование постеров, бэкдропов и фото персон Vault."
  },
  {
    id: "player",
    title: "Плеер",
    group: "Медиа",
    description:
      "Кнопка «Смотреть»: запуск VLC на компьютере через протокол mfp:// и правила перевода путей Plex в UNC."
  },
  {
    id: "tmdb",
    title: "TMDB",
    group: "Метаданные",
    description: "Ключи и токены TMDB. Authenticated token остаётся readonly."
  },
  {
    id: "omdb",
    title: "OMDB",
    group: "Метаданные",
    description: "Ключ OMDB API для рейтингов IMDb, Rotten Tomatoes и Metacritic."
  },
  {
    id: "websearch",
    title: "Web Search",
    group: "Метаданные",
    description:
      "Веб-поиск для умного поиска TMDB. SearXNG URL имеет приоритет: если задан — Tavily не нужен. Без одного из них очередь TMDB sync не стартует."
  },
  {
    id: "writeback",
    title: "TMDB Write-back",
    group: "Метаданные",
    description: "Обратная синхронизация Vault → TMDB (watchlist/favorite/rating). Работает через tmdb_adapter."
  },
  {
    id: "local-ai",
    title: "AI",
    group: "AI",
    description:
      "Endpoints — шаблоны подключений к OpenAI-совместимым серверам: локальным (Ollama / LM Studio / Lemonade / Unsloth) и облачным (Groq и т.п.). Один endpoint выбирается активным."
  },
  {
    id: "kinorium-sync",
    title: "Kinorium sync",
    group: "AI",
    description:
      "Какой AI-сервер используют быстрая и глубокая стадии TMDB-матчинга. Пусто — используется выбранный endpoint из раздела AI."
  },
  {
    id: "taste",
    title: "Taste",
    group: "AI",
    description:
      "Профили вкусов для AI-предсказания. Один профиль — один человек: вставьте текст вида rita_profile.md или загрузите файл."
  },
  {
    id: "account",
    title: "Аккаунт",
    group: "Прочее",
    description: "Смена пароля текущего пользователя."
  },
  {
    id: "diagnostics",
    title: "Диагностика",
    group: "Прочее",
    description: "Быстрые сигналы по текущему состоянию настроек."
  }
];

const SECTION_IDS = new Set<string>(PREFERENCES_SECTIONS.map((item) => item.id));

// В ?section= принимаем только реальные id разделов, без синонимов.
export const resolveSectionId = (raw: string | null | undefined): PreferencesSectionId | null => {
  if (!raw) return null;
  const normalized = raw.trim().toLowerCase();
  return SECTION_IDS.has(normalized) ? (normalized as PreferencesSectionId) : null;
};

// Какой раздел отвечает за какое поле payload — для индикаторов «изменено» в навигации.
export const FIELD_SECTIONS: Record<keyof PreferencesUpdatePayload, PreferencesSectionId> = {
  last_scan: "kinozal",
  scan_interval_minutes: "kinozal",
  cookie_pass: "kinozal",
  cookie_uid: "kinozal",
  kinozal_domain: "kinozal",
  kinozal_mirrors: "kinozal",
  countries: "rules",
  genres: "rules",
  max_year: "rules",
  min_rating: "rules",
  low_countries: "rules",
  low_genres: "rules",
  low_max_year: "rules",
  low_min_rating: "rules",
  ignore_title: "rules",
  qbt_url: "qbittorrent",
  qbt_api_key: "qbittorrent",
  qbt_skip_cert_verify: "qbittorrent",
  torrents_backup_folder: "qbittorrent",
  plex_address: "plex",
  plex_token: "plex",
  vault_image_cache_enabled: "images",
  player_enabled: "player",
  player_path_map: "player",
  tmdb_api_key: "tmdb",
  tmdb_v4_read_access_token: "tmdb",
  omdb_api_key: "omdb",
  tavily_api_key: "websearch",
  searxng_url: "websearch",
  ai_enabled: "local-ai",
  kinorium_fast_ai_endpoint_id: "kinorium-sync",
  kinorium_deep_ai_endpoint_id: "kinorium-sync"
};

const asText = (value: string | number | null | undefined) => (value ?? "").toString();
const asOptionalText = (value: string) => {
  const normalized = value.trim();
  return normalized ? normalized : null;
};
const asOptionalSecret = (value: string) => (value ? value : null);
const asOptionalInt = (value: string) => {
  const normalized = Number.parseInt(value, 10);
  return Number.isFinite(normalized) ? normalized : null;
};
const asNumber = (value: string, fallback: number) => {
  const normalized = Number.parseFloat(value);
  return Number.isFinite(normalized) ? normalized : fallback;
};

export const createFormState = (preferences: PreferencesData): PreferencesFormState => {
  const mirrors = preferences.kinozal_mirrors ?? [];
  const domain = preferences.kinozal_domain ?? "";
  return {
    last_scan: preferences.last_scan ?? "",
    scan_schedule_enabled: preferences.scan_interval_minutes != null,
    scan_interval_minutes: asText(preferences.scan_interval_minutes ?? MIN_SCAN_INTERVAL_MINUTES),
    countries: preferences.countries,
    genres: preferences.genres,
    max_year: asText(preferences.max_year),
    min_rating: asText(preferences.min_rating),
    low_countries: preferences.low_countries,
    low_genres: preferences.low_genres,
    low_max_year: asText(preferences.low_max_year),
    low_min_rating: asText(preferences.low_min_rating),
    plex_address: preferences.plex_address ?? "",
    plex_token: preferences.plex_token ?? "",
    cookie_pass: preferences.cookie_pass ?? "",
    cookie_uid: preferences.cookie_uid ?? "",
    // Активное зеркало всегда одно из зеркал в списке (инвариант бэкенда).
    kinozal_domain: mirrors.includes(domain) ? domain : "",
    kinozal_mirrors: mirrors,
    qbt_url: preferences.qbt_url ?? "",
    qbt_api_key: preferences.qbt_api_key ?? "",
    qbt_skip_cert_verify: preferences.qbt_skip_cert_verify ?? false,
    torrents_backup_folder: preferences.torrents_backup_folder ?? "",
    ignore_title: preferences.ignore_title,
    tmdb_api_key: preferences.tmdb_api_key ?? "",
    omdb_api_key: preferences.omdb_api_key ?? "",
    tavily_api_key: preferences.tavily_api_key ?? "",
    searxng_url: preferences.searxng_url ?? "",
    tmdb_v4_read_access_token: preferences.tmdb_v4_read_access_token ?? "",
    ai_enabled: preferences.ai_enabled ?? false,
    kinorium_fast_ai_endpoint_id: asText(preferences.kinorium_fast_ai_endpoint_id),
    kinorium_deep_ai_endpoint_id: asText(preferences.kinorium_deep_ai_endpoint_id),
    vault_image_cache_enabled: preferences.vault_image_cache_enabled ?? true,
    player_enabled: preferences.player_enabled ?? true,
    player_path_map: preferences.player_path_map ?? ""
  };
};

export const buildPayload = (formState: PreferencesFormState): PreferencesUpdatePayload => ({
  last_scan: formState.last_scan.trim() || null,
  scan_interval_minutes: formState.scan_schedule_enabled
    ? Math.max(
        MIN_SCAN_INTERVAL_MINUTES,
        Number.parseInt(formState.scan_interval_minutes, 10) || MIN_SCAN_INTERVAL_MINUTES
      )
    : null,
  countries: formState.countries.trim(),
  genres: formState.genres.trim(),
  max_year: asNumber(formState.max_year, 1990),
  min_rating: asNumber(formState.min_rating, 3),
  low_countries: formState.low_countries.trim(),
  low_genres: formState.low_genres.trim(),
  low_max_year: asNumber(formState.low_max_year, 2000),
  low_min_rating: asNumber(formState.low_min_rating, 5),
  plex_address: asOptionalText(formState.plex_address),
  plex_token: asOptionalText(formState.plex_token),
  cookie_pass: asOptionalText(formState.cookie_pass),
  cookie_uid: asOptionalText(formState.cookie_uid),
  kinozal_domain: asOptionalText(formState.kinozal_domain),
  kinozal_mirrors: formState.kinozal_mirrors,
  qbt_url: asOptionalText(formState.qbt_url),
  qbt_api_key: asOptionalSecret(formState.qbt_api_key),
  qbt_skip_cert_verify: formState.qbt_skip_cert_verify,
  torrents_backup_folder: asOptionalText(formState.torrents_backup_folder),
  ignore_title: formState.ignore_title.trim(),
  tmdb_api_key: asOptionalText(formState.tmdb_api_key),
  omdb_api_key: asOptionalText(formState.omdb_api_key),
  tavily_api_key: asOptionalText(formState.tavily_api_key),
  searxng_url: asOptionalText(formState.searxng_url),
  tmdb_v4_read_access_token: asOptionalText(formState.tmdb_v4_read_access_token),
  ai_enabled: formState.ai_enabled,
  kinorium_fast_ai_endpoint_id: asOptionalInt(formState.kinorium_fast_ai_endpoint_id),
  kinorium_deep_ai_endpoint_id: asOptionalInt(formState.kinorium_deep_ai_endpoint_id),
  vault_image_cache_enabled: formState.vault_image_cache_enabled,
  player_enabled: formState.player_enabled,
  player_path_map: formState.player_path_map
});

export const payloadSnapshot = (formState: PreferencesFormState) => JSON.stringify(buildPayload(formState));

export const changedFields = (
  formState: PreferencesFormState,
  initialSnapshot: string
): (keyof PreferencesUpdatePayload)[] => {
  let baseline: Record<string, unknown>;
  try {
    baseline = JSON.parse(initialSnapshot) as Record<string, unknown>;
  } catch {
    return [];
  }
  const current = buildPayload(formState) as Record<string, unknown>;
  return (Object.keys(current) as (keyof PreferencesUpdatePayload)[]).filter(
    (key) => JSON.stringify(current[key]) !== JSON.stringify(baseline[key])
  );
};

export const dirtySections = (
  formState: PreferencesFormState,
  initialSnapshot: string
): Map<PreferencesSectionId, number> => {
  const counts = new Map<PreferencesSectionId, number>();
  for (const field of changedFields(formState, initialSnapshot)) {
    const section = FIELD_SECTIONS[field];
    if (!section) continue;
    counts.set(section, (counts.get(section) ?? 0) + 1);
  }
  return counts;
};
