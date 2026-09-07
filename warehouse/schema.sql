-- Facts only. Not one aggregate, not one ratio, not one percentage.
--
-- Every metric is defined in semantic/catalogs/*.yml and computed at query
-- time. A percentage stored in a column is locked to one grain and cannot be
-- recomputed correctly at another -- AVG(per-row %) is not SUM(a)/SUM(b).
-- See docs/oikea-vs-laskennallinen.md.

create or replace table dim_lifters as
select
    lifter_id,
    lifter_name
from read_csv('data/lifters.csv', header = true, delim = ',', columns = {
    'lifter_id': 'VARCHAR',
    'lifter_name': 'VARCHAR'
});

create or replace table dim_challenges as
select
    challenge_id,
    challenge_name,
    goal_total_1rm_kg,
    start_date,
    end_date
from read_csv('data/challenges.csv', header = true, delim = ',', columns = {
    'challenge_id': 'VARCHAR',
    'challenge_name': 'VARCHAR',
    'goal_total_1rm_kg': 'DOUBLE',
    'start_date': 'DATE',
    'end_date': 'DATE'
});

-- Which lifter belongs to which challenge, and the personal target they set
-- there. A lifter who is in no challenge has no row here. That is on purpose:
-- it is the orphan case every reporting system has, and the metrics must
-- neither include them silently nor lose track of them. See docs/rajaus.md.
create or replace table bridge_memberships as
select
    challenge_id,
    lifter_id,
    target_1rm_kg,
    starting_1rm_kg
from read_csv('data/memberships.csv', header = true, delim = ',', columns = {
    'challenge_id': 'VARCHAR',
    'lifter_id': 'VARCHAR',
    'target_1rm_kg': 'DOUBLE',
    'starting_1rm_kg': 'DOUBLE'
});

-- Grain: one logged set.
--
-- one_rm_kg is derived per row, never aggregated here. Brzycki:
--     1RM = weight * 36 / (37 - reps)
-- Same formula as penkkikarnevaalit-analytics/models/staging/stg_workouts.sql.
--
-- At reps = 1 the factor is 36/36 = 1.0 exactly, so the number IS the weight
-- lifted: an observation, not a model output. Every other rep count produces
-- an estimate. one_rm_source records which, because a total that mixes the two
-- hides the difference.
create or replace table fct_lifts as
select
    lift_id,
    lifter_id,
    lift_date,
    weight_kg,
    reps,
    round(weight_kg * 36.0 / (37.0 - reps), 1) as one_rm_kg,
    case when reps = 1 then 'true_max' else 'brzycki_estimate' end as one_rm_source
from read_csv('data/lifts.csv', header = true, delim = ',', columns = {
    'lift_id': 'VARCHAR',
    'lifter_id': 'VARCHAR',
    'lift_date': 'DATE',
    'weight_kg': 'DOUBLE',
    'reps': 'INTEGER'
})
-- Brzycki is only reliable to about 12 reps. Dropping heavier-rep sets is a
-- DECISION, not a technical detail, so it is stated in the catalogue note and
-- counted in warehouse/build.py rather than filtered away in silence.
where reps between 1 and 12
  and weight_kg > 0;

-- The most recent logged set per lifter. "Current 1RM" means latest, not best:
-- a lifter who had a great day in March and has declined since should show the
-- decline. Ties on date are broken by lift_id so the view is deterministic.
create or replace view fct_latest_lift as
select lift_id, lifter_id, lift_date, weight_kg, reps, one_rm_kg, one_rm_source
from (
    select *, row_number() over (
        partition by lifter_id order by lift_date desc, lift_id desc
    ) as rn
    from fct_lifts
)
where rn = 1;
