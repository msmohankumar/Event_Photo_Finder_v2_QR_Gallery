
CREATE TABLE IF NOT EXISTS public.event_config (

    id INTEGER PRIMARY KEY DEFAULT 1,

    event_name TEXT NOT NULL DEFAULT 'Event Gallery',

    provider TEXT NOT NULL DEFAULT 'drive',

    folder_url TEXT NOT NULL DEFAULT '',

    threshold NUMERIC NOT NULL DEFAULT 0.40,

    enabled BOOLEAN NOT NULL DEFAULT FALSE
);


INSERT INTO public.event_config (

    id,

    event_name,

    provider,

    folder_url,

    threshold,

    enabled

)

VALUES (

    1,

    'Event Gallery',

    'drive',

    '',

    0.40,

    FALSE

)

ON CONFLICT (id) DO NOTHING;


ALTER TABLE public.event_config

ENABLE ROW LEVEL SECURITY;
