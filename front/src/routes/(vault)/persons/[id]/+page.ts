import { error } from "@sveltejs/kit";
import type { PageLoad } from "./$types";

type PersonMovie = {
  id: number;
  title: string;
  original_title: string | null;
  title_en: string | null;
  slug: string;
  year: number | null;
  poster_url: string | null;
  roles: string[];
  credits: { role: string; role_display: string; character_names: string[] }[];
  character_names: string[];
  watch_status: "watched" | "will_watch" | "wont_watch" | null;
  rating: number | null;
  is_favorite: boolean;
};

type PersonImage = {
  file_path: string;
  url: string | null;
  full_url: string | null;
  thumb_url: string | null;
};

type PersonDetail = {
  id: number;
  name: string;
  original_name: string;
  tmdb_id: string | null;
  imdb_id: string | null;
  photo_url: string | null;
  photo_full_url: string | null;
  biography: string;
  birth_date: string | null;
  death_date: string | null;
  place_of_birth: string | null;
  known_for_department: string | null;
  also_known_as: string[];
  gender: string | null;
  gender_display: string | null;
  movies_count: number;
  roles_count: number;
  career_years: number;
  filmography: PersonMovie[];
  actor_count: number;
  director_count: number;
  producer_count: number;
  is_favorite: boolean;
  is_star: boolean;
};

// Фото персоны тянем из TMDB API, поэтому ограничиваем ожидание: страница
// не должна зависать, если TMDB недоступен. Фото тогда просто не будет.
const PERSON_IMAGES_TIMEOUT_MS = 5000;

type PersonImagesResult = {
  images: PersonImage[];
  imagesError: string;
};

async function loadPersonImages(
  fetchFn: typeof fetch,
  personId: string
): Promise<PersonImagesResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PERSON_IMAGES_TIMEOUT_MS);

  try {
    const response = await fetchFn(`/api/vault/persons/${personId}/images?limit=8`, {
      signal: controller.signal
    });
    const payload = (await response.json().catch(() => ({}))) as {
      items?: PersonImage[];
      error?: string | null;
    };

    if (!response.ok) {
      return {
        images: [],
        imagesError: payload.error ?? `HTTP ${response.status}`
      };
    }

    return {
      images: Array.isArray(payload.items) ? payload.items : [],
      imagesError: payload.error ?? ""
    };
  } catch (err) {
    return {
      images: [],
      imagesError:
        err instanceof Error && err.name !== "AbortError"
          ? err.message
          : "Не удалось загрузить фото"
    };
  } finally {
    clearTimeout(timeout);
  }
}

export const load: PageLoad = async ({ fetch, params }) => {
  // Оба запроса стартуют одновременно: данные персоны (БД) и список фото
  // (кеш/ TMDB). Раньше фото запрашивались уже после рендера страницы и
  // стартовали позже постеров фильмографии.
  const personPromise = fetch(`/api/vault/persons/${params.id}`);
  const imagesPromise = loadPersonImages(fetch, params.id);

  const response = await personPromise;
  if (response.status === 404) {
    throw error(404, "Person not found");
  }
  if (!response.ok) {
    throw error(response.status, `API error: ${response.status}`);
  }

  const person = (await response.json()) as PersonDetail;
  const { images, imagesError } = await imagesPromise;

  return { person, images, imagesError };
};
