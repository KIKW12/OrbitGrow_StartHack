import { type ClientSchema, a, defineData } from '@aws-amplify/backend';

const schema = a.schema({
  MissionState: a
    .model({
      current_sol: a.integer(),
      phase: a.string(),
      last_updated: a.datetime(),
    })
    .authorization((allow) => [allow.authenticated().to(['read'])]),

  GreenhousePlot: a
    .model({
      plot_id: a.string(),
      crop: a.string(),
      planted_sol: a.integer(),
      harvest_sol: a.integer(),
      area_m2: a.float(),
      health: a.float(),
      stress_flags: a.string().array(),
    })
    .authorization((allow) => [allow.authenticated().to(['read'])]),

  SolReport: a
    .model({
      sol: a.integer(),
      nutrition_score: a.float(),
      kcal_produced: a.float(),
      protein_g: a.float(),
      water_efficiency: a.float(),
      energy_used: a.float(),
      agent_decisions: a.json(),
      crises_active: a.string().array(),
    })
    .authorization((allow) => [allow.authenticated().to(['read'])]),

  NutritionLedger: a
    .model({
      sol: a.integer(),
      kcal: a.float(),
      protein_g: a.float(),
      vitamin_a: a.float(),
      vitamin_c: a.float(),
      vitamin_k: a.float(),
      folate: a.float(),
      coverage_score: a.float(),
    })
    .authorization((allow) => [allow.authenticated().to(['read'])]),

  CrewHealth: a
    .model({
      astronaut: a.string(),
      sol: a.integer(),
      kcal_received: a.float(),
      protein_g: a.float(),
      vitamin_a: a.float(),
      vitamin_c: a.float(),
      vitamin_k: a.float(),
      folate: a.float(),
      health_score: a.float(),
      deficit_flags: a.string().array(),
    })
    .authorization((allow) => [allow.authenticated().to(['read'])]),

  EnvironmentState: a
    .model({
      sol: a.integer(),
      temperature_c: a.float(),
      humidity_pct: a.float(),
      co2_ppm: a.float(),
      light_umol: a.float(),
      water_efficiency_pct: a.float(),
      energy_used_pct: a.float(),
      external_temp_c: a.float(),
      dust_storm_index: a.float(),
      radiation_msv: a.float(),
    })
    .authorization((allow) => [allow.authenticated().to(['read'])]),
});

export type Schema = ClientSchema<typeof schema>;

export const data = defineData({
  schema,
  authorizationModes: {
    defaultAuthorizationMode: 'userPool',
  },
});
