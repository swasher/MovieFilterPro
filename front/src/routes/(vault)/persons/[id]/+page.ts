import { error } from "@sveltejs/kit";
import type { PageLoad } from "./$types";

type PersonMovie = {
  id: number;
  title: string;
  slug: string;
  year: number | null;
  poster_url: string | null;
  roles: string[];
  character_names: string[];
  watch_status: "watched" | "will_watch" | "wont_watch" | null;
  rating: number | null;
  is_favorite: boolean;
};

type PersonDetail = {
  id: number;
  name: string;
  original_name: string;
  tmdb_id: string | null;
  imdb_id: string | null;
  photo_url: string | null;
  biography: string;
  birth_date: string | null;
  death_date: string | null;
  country: string | null;
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
};

export const load: PageLoad = async ({ fetch, params }) => {
  const response = await fetch(`/api/vault/persons/${params.id}`);
  if (response.status === 404) {
    throw error(404, "Person not found");
  }
  if (!response.ok) {
    throw error(response.status, `API error: ${response.status}`);
  }

  const person = (await response.json()) as PersonDetail;
  return { person };
};
