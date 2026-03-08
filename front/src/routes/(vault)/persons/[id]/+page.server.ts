import { error } from "@sveltejs/kit";
import type { PageServerLoad } from "./$types";
import { djangoFetch } from "$lib/server/django";

type PersonMovie = {
  id: number;
  title: string;
  slug: string;
  year: number | null;
  poster_url: string | null;
  role: string;
  role_display: string;
  character_name: string | null;
};

type PersonDetail = {
  id: number;
  name: string;
  original_name: string;
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
};

export const load: PageServerLoad = async (event) => {
  const response = await djangoFetch(event, `/api/vault/persons/${event.params.id}`);
  if (response.status === 404) {
    throw error(404, "Person not found");
  }
  if (!response.ok) {
    throw error(response.status, `API error: ${response.status}`);
  }

  const person = (await response.json()) as PersonDetail;
  return { person };
};
