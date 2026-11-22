-- 001_schema.sql: esquema do Decide.ai (gerado por backend/scripts/build_migrations.py)
-- Tabelas do docx: restaurants, groups, participants, preferences, recommendations, votes,
-- reservations, reviews; mais events para as métricas do funil.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS groups (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	invite_code VARCHAR(12) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	occasion VARCHAR(40), 
	event_date DATE NOT NULL, 
	event_time VARCHAR(5) NOT NULL, 
	budget_per_person NUMERIC(8, 2) NOT NULL, 
	party_size INTEGER NOT NULL, 
	neighborhood VARCHAR(60) NOT NULL, 
	city VARCHAR(60) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	current_round INTEGER NOT NULL, 
	vote_deadline TIMESTAMP WITH TIME ZONE, 
	organizer_token_hash VARCHAR(64) NOT NULL, 
	match_summary JSONB, 
	winner_recommendation_id UUID, 
	decision_note TEXT, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	is_demo BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_groups_status CHECK (status IN ('coletando_preferencias', 'match_disponivel', 'votacao_aberta', 'escolha_concluida', 'reserva_simulada', 'avaliado')), 
	CONSTRAINT ck_groups_budget CHECK (budget_per_person > 0), 
	CONSTRAINT ck_groups_party_size CHECK (party_size BETWEEN 2 AND 20), 
	CONSTRAINT ck_groups_round CHECK (current_round >= 0), 
	UNIQUE (invite_code)
);

CREATE TABLE IF NOT EXISTS restaurants (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	slug VARCHAR(120) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	cuisine_type VARCHAR(40) NOT NULL, 
	description TEXT NOT NULL, 
	neighborhood VARCHAR(60) NOT NULL, 
	city VARCHAR(60) NOT NULL, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	avg_price NUMERIC(8, 2) NOT NULL, 
	dietary_options JSONB NOT NULL, 
	capacity INTEGER NOT NULL, 
	ambiences JSONB NOT NULL, 
	opening_hours JSONB NOT NULL, 
	availability_rate FLOAT NOT NULL, 
	rating FLOAT NOT NULL, 
	rating_count INTEGER NOT NULL, 
	simulated_benefit TEXT, 
	accepts_reservation BOOLEAN NOT NULL, 
	is_fictional BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_restaurants_price CHECK (avg_price > 0), 
	CONSTRAINT ck_restaurants_capacity CHECK (capacity >= 2), 
	CONSTRAINT ck_restaurants_rating CHECK (rating BETWEEN 1 AND 5), 
	CONSTRAINT ck_restaurants_availability CHECK (availability_rate > 0 AND availability_rate <= 1), 
	CONSTRAINT ck_restaurants_fictional CHECK (is_fictional = true), 
	UNIQUE (slug), 
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS participants (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	group_id UUID NOT NULL, 
	nickname VARCHAR(30) NOT NULL, 
	nickname_key VARCHAR(30) NOT NULL, 
	location VARCHAR(60), 
	is_organizer BOOLEAN NOT NULL, 
	is_simulated BOOLEAN NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_participants_nickname UNIQUE (group_id, nickname_key), 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE, 
	UNIQUE (token_hash)
);

CREATE TABLE IF NOT EXISTS recommendations (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	group_id UUID NOT NULL, 
	restaurant_id UUID NOT NULL, 
	round_number INTEGER NOT NULL, 
	rank INTEGER NOT NULL, 
	score FLOAT NOT NULL, 
	mean_score FLOAT NOT NULL, 
	penalty FLOAT NOT NULL, 
	breakdown JSONB NOT NULL, 
	highlights JSONB NOT NULL, 
	attention_point TEXT NOT NULL, 
	avg_distance_km FLOAT NOT NULL, 
	reason TEXT NOT NULL, 
	reason_source VARCHAR(10) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_recommendations_rank UNIQUE (group_id, round_number, rank), 
	CONSTRAINT uq_recommendations_restaurant UNIQUE (group_id, round_number, restaurant_id), 
	CONSTRAINT ck_recommendations_score CHECK (score BETWEEN 0 AND 100), 
	CONSTRAINT ck_recommendations_rank CHECK (rank BETWEEN 1 AND 3), 
	CONSTRAINT ck_recommendations_source CHECK (reason_source IN ('ia', 'fallback')), 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE, 
	FOREIGN KEY(restaurant_id) REFERENCES restaurants (id)
);

CREATE TABLE IF NOT EXISTS events (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	name VARCHAR(40) NOT NULL, 
	group_id UUID, 
	participant_id UUID, 
	properties JSONB NOT NULL, 
	is_demo BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE SET NULL, 
	FOREIGN KEY(participant_id) REFERENCES participants (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_events_name_group ON events (name, group_id);

CREATE TABLE IF NOT EXISTS preferences (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	participant_id UUID NOT NULL, 
	cuisines JSONB NOT NULL, 
	dietary_restrictions JSONB NOT NULL, 
	ambience JSONB NOT NULL, 
	max_distance FLOAT NOT NULL, 
	max_budget NUMERIC(8, 2), 
	additional_preferences TEXT, 
	free_text TEXT, 
	parsed_by VARCHAR(10), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_preferences_distance CHECK (max_distance > 0 AND max_distance <= 60), 
	CONSTRAINT ck_preferences_budget CHECK (max_budget IS NULL OR max_budget > 0), 
	UNIQUE (participant_id), 
	FOREIGN KEY(participant_id) REFERENCES participants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reservations (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	group_id UUID NOT NULL, 
	restaurant_id UUID NOT NULL, 
	recommendation_id UUID NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	booking_time TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	party_size INTEGER NOT NULL, 
	confirmation_code VARCHAR(20) NOT NULL, 
	is_simulated BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_reservations_simulated CHECK (is_simulated = true), 
	CONSTRAINT ck_reservations_status CHECK (status IN ('confirmada', 'cancelada')), 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE, 
	FOREIGN KEY(restaurant_id) REFERENCES restaurants (id), 
	FOREIGN KEY(recommendation_id) REFERENCES recommendations (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_one_confirmed ON reservations (group_id) WHERE status = 'confirmada';

CREATE TABLE IF NOT EXISTS votes (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	participant_id UUID NOT NULL, 
	recommendation_id UUID NOT NULL, 
	group_id UUID NOT NULL, 
	round_number INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_votes_participant_round UNIQUE (participant_id, round_number), 
	FOREIGN KEY(participant_id) REFERENCES participants (id) ON DELETE CASCADE, 
	FOREIGN KEY(recommendation_id) REFERENCES recommendations (id) ON DELETE CASCADE, 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	reservation_id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	rating INTEGER NOT NULL, 
	comment TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_reviews_rating CHECK (rating BETWEEN 1 AND 5), 
	CONSTRAINT uq_reviews_participant UNIQUE (reservation_id, participant_id), 
	FOREIGN KEY(reservation_id) REFERENCES reservations (id) ON DELETE CASCADE, 
	FOREIGN KEY(participant_id) REFERENCES participants (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_fk_1 ON participants (group_id);
CREATE INDEX IF NOT EXISTS ix_fk_2 ON preferences (participant_id);
CREATE INDEX IF NOT EXISTS ix_fk_3 ON recommendations (group_id, round_number);
CREATE INDEX IF NOT EXISTS ix_fk_4 ON votes (group_id, round_number);
CREATE INDEX IF NOT EXISTS ix_fk_5 ON reservations (group_id);
CREATE INDEX IF NOT EXISTS ix_fk_6 ON reviews (reservation_id);

-- groups.winner_recommendation_id -> recommendations.id (referência circular, criada depois).
DO $$ BEGIN
  ALTER TABLE groups ADD CONSTRAINT fk_groups_winner FOREIGN KEY (winner_recommendation_id)
    REFERENCES recommendations (id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- updated_at mantido pelo banco em qualquer UPDATE.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_groups_updated_at ON groups;
CREATE TRIGGER trg_groups_updated_at BEFORE UPDATE ON groups FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_restaurants_updated_at ON restaurants;
CREATE TRIGGER trg_restaurants_updated_at BEFORE UPDATE ON restaurants FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_participants_updated_at ON participants;
CREATE TRIGGER trg_participants_updated_at BEFORE UPDATE ON participants FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_recommendations_updated_at ON recommendations;
CREATE TRIGGER trg_recommendations_updated_at BEFORE UPDATE ON recommendations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_preferences_updated_at ON preferences;
CREATE TRIGGER trg_preferences_updated_at BEFORE UPDATE ON preferences FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_reservations_updated_at ON reservations;
CREATE TRIGGER trg_reservations_updated_at BEFORE UPDATE ON reservations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_votes_updated_at ON votes;
CREATE TRIGGER trg_votes_updated_at BEFORE UPDATE ON votes FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_reviews_updated_at ON reviews;
CREATE TRIGGER trg_reviews_updated_at BEFORE UPDATE ON reviews FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Segurança: o Supabase expõe o schema public pela Data API com a chave anon. O app não usa essa
-- API (só o backend acessa o banco, com o usuário postgres, que ignora RLS). Ativar RLS sem
-- nenhuma policy bloqueia qualquer acesso pela chave anon ou authenticated.

ALTER TABLE groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurants ENABLE ROW LEVEL SECURITY;
ALTER TABLE participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
