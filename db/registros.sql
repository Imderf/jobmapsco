-- Registros del Mapa del Empleo (Supabase / Postgres). Pegar en Supabase → SQL Editor → Run.
-- La página (rol anon) solo puede INSERTAR. Leer, editar o borrar: desde el panel de Supabase (Table Editor) o con la llave service_role.
create table if not exists public.registros (
  id bigint generated always as identity primary key,
  nombre text not null check (char_length(nombre) between 1 and 80),
  correo text not null unique check (char_length(correo) <= 120 and correo = lower(correo) and correo ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  acepto boolean not null check (acepto),                -- consentimiento (Ley 1581 de 2012)
  politica text not null check (char_length(politica) <= 80),   -- versión de la política que aceptó
  creado timestamptz not null default now()
);

alter table public.registros enable row level security;
revoke all on public.registros from anon, authenticated;
grant insert (nombre, correo, acepto, politica) on public.registros to anon;
drop policy if exists "la pagina solo inserta" on public.registros;
create policy "la pagina solo inserta" on public.registros for insert to anon with check (acepto);
