ALTER TABLE public.strategies DROP CONSTRAINT IF EXISTS strategies_type_check;
ALTER TABLE public.strategies ADD CONSTRAINT strategies_type_check CHECK (type IN ('builtin', 'custom_python', 'visual', 'visual_builder'));
