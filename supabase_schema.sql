create table if not exists public.event_config (
  id integer primary key default 1,
  event_name text not null default 'Event Gallery',
  provider text not null default 'drive',
  folder_url text not null default '',
  threshold numeric not null default 0.40,
  enabled boolean not null default true
);

-- Insert initial row
insert into public.event_config (id, event_name, provider, folder_url, threshold, enabled)
values (1, 'Event Gallery', 'drive', '', 0.40, false)
on conflict (id) do nothing;

-- For a prototype, allow the configured Supabase key to access this table.
-- Prefer a server-side service role key stored only in Streamlit secrets;
-- never expose it to guests or commit it to GitHub.
alter table public.event_config enable row level security;
