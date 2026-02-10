-- ============================================================================
-- ROS DEMO DATA: Workloads & Recommendations for 8 clusters
-- Populates costonprem_ros database for the Optimizations tab
-- ============================================================================

-- 1. CLUSTERS (one per source)
INSERT INTO clusters (id, tenant_id, source_id, cluster_uuid, cluster_alias, last_reported_at)
VALUES
  (1, 1, '16', 'prod-data-pipeline',     'prod-data-pipeline',     '2026-02-06 00:00:00+00'),
  (2, 1, '11', 'prod-api-gateway',       'prod-api-gateway',       '2026-02-06 00:00:00+00'),
  (3, 1,  '9', 'prod-ecommerce-us-east', 'prod-ecommerce-us-east', '2026-02-06 00:00:00+00'),
  (4, 1, '10', 'prod-ecommerce-eu',      'prod-ecommerce-eu',      '2026-02-06 00:00:00+00'),
  (5, 1, '12', 'staging-performance',    'staging-performance',    '2026-02-06 00:00:00+00'),
  (6, 1, '15', 'qa-automation',          'qa-automation',          '2026-02-06 00:00:00+00'),
  (7, 1, '13', 'dev-feature-team-a',     'dev-feature-team-a',     '2026-02-06 00:00:00+00'),
  (8, 1, '14', 'dev-feature-team-b',     'dev-feature-team-b',     '2026-02-06 00:00:00+00')
ON CONFLICT DO NOTHING;

-- Reset sequence
SELECT setval('clusters_id_seq', 10);

-- 2. WORKLOADS (3-5 per cluster, realistic microservice names)
INSERT INTO workloads (id, org_id, cluster_id, experiment_name, namespace, workload_type, workload_name, containers, metrics_upload_at)
VALUES
  -- prod-data-pipeline (cluster 1): heavy data processing workloads
  ( 1, 'org1234567', 1, 'org1234567;16;prod-data-pipeline;data-processing;deployment;spark-executor',     'data-processing', 'deployment', 'spark-executor',     '{spark-executor,sidecar-log}',    '2026-02-06 00:00:00+00'),
  ( 2, 'org1234567', 1, 'org1234567;16;prod-data-pipeline;data-processing;deployment;kafka-streams',      'data-processing', 'deployment', 'kafka-streams',      '{kafka-streams}',                  '2026-02-06 00:00:00+00'),
  ( 3, 'org1234567', 1, 'org1234567;16;prod-data-pipeline;data-processing;deployment;flink-taskmanager',  'data-processing', 'deployment', 'flink-taskmanager',  '{flink-taskmanager}',              '2026-02-06 00:00:00+00'),
  ( 4, 'org1234567', 1, 'org1234567;16;prod-data-pipeline;monitoring;deployment;prometheus',               'monitoring',      'deployment', 'prometheus',         '{prometheus,config-reloader}',     '2026-02-06 00:00:00+00'),

  -- prod-api-gateway (cluster 2): API-heavy workloads
  ( 5, 'org1234567', 2, 'org1234567;11;prod-api-gateway;api-gateway;deployment;envoy-proxy',              'api-gateway',     'deployment', 'envoy-proxy',        '{envoy-proxy,config-watcher}',    '2026-02-06 00:00:00+00'),
  ( 6, 'org1234567', 2, 'org1234567;11;prod-api-gateway;api-gateway;deployment;rate-limiter',             'api-gateway',     'deployment', 'rate-limiter',       '{rate-limiter}',                   '2026-02-06 00:00:00+00'),
  ( 7, 'org1234567', 2, 'org1234567;11;prod-api-gateway;auth;deployment;keycloak',                        'auth',            'deployment', 'keycloak',           '{keycloak}',                       '2026-02-06 00:00:00+00'),

  -- prod-ecommerce-us-east (cluster 3)
  ( 8, 'org1234567', 3, 'org1234567;9;prod-ecommerce-us-east;ecommerce;deployment;product-catalog',       'ecommerce',       'deployment', 'product-catalog',    '{product-catalog,redis-cache}',   '2026-02-06 00:00:00+00'),
  ( 9, 'org1234567', 3, 'org1234567;9;prod-ecommerce-us-east;ecommerce;deployment;checkout-service',      'ecommerce',       'deployment', 'checkout-service',   '{checkout-service}',               '2026-02-06 00:00:00+00'),
  (10, 'org1234567', 3, 'org1234567;9;prod-ecommerce-us-east;ecommerce;deployment;search-engine',         'ecommerce',       'deployment', 'search-engine',      '{elasticsearch,search-api}',      '2026-02-06 00:00:00+00'),

  -- prod-ecommerce-eu (cluster 4)
  (11, 'org1234567', 4, 'org1234567;10;prod-ecommerce-eu;ecommerce;deployment;product-catalog',            'ecommerce',       'deployment', 'product-catalog',    '{product-catalog,redis-cache}',   '2026-02-06 00:00:00+00'),
  (12, 'org1234567', 4, 'org1234567;10;prod-ecommerce-eu;ecommerce;deployment;payment-processor',          'ecommerce',       'deployment', 'payment-processor',  '{payment-processor}',              '2026-02-06 00:00:00+00'),

  -- staging-performance (cluster 5)
  (13, 'org1234567', 5, 'org1234567;12;staging-performance;load-testing;deployment;locust-worker',          'load-testing',    'deployment', 'locust-worker',      '{locust-worker}',                  '2026-02-06 00:00:00+00'),
  (14, 'org1234567', 5, 'org1234567;12;staging-performance;staging;deployment;app-server',                  'staging',         'deployment', 'app-server',         '{app-server,nginx}',              '2026-02-06 00:00:00+00'),

  -- qa-automation (cluster 6)
  (15, 'org1234567', 6, 'org1234567;15;qa-automation;qa;deployment;selenium-runner',                        'qa',              'deployment', 'selenium-runner',    '{selenium-runner,chrome-driver}',  '2026-02-06 00:00:00+00'),
  (16, 'org1234567', 6, 'org1234567;15;qa-automation;qa;deployment;test-orchestrator',                      'qa',              'deployment', 'test-orchestrator',  '{test-orchestrator}',              '2026-02-06 00:00:00+00'),

  -- dev-feature-team-a (cluster 7)
  (17, 'org1234567', 7, 'org1234567;13;dev-feature-team-a;development;deployment;backend-api',              'development',     'deployment', 'backend-api',        '{backend-api,debug-sidecar}',     '2026-02-06 00:00:00+00'),
  (18, 'org1234567', 7, 'org1234567;13;dev-feature-team-a;development;deployment;frontend-app',             'development',     'deployment', 'frontend-app',       '{frontend-app}',                   '2026-02-06 00:00:00+00'),

  -- dev-feature-team-b (cluster 8)
  (19, 'org1234567', 8, 'org1234567;14;dev-feature-team-b;development;deployment;microservice-a',           'development',     'deployment', 'microservice-a',     '{microservice-a}',                 '2026-02-06 00:00:00+00'),
  (20, 'org1234567', 8, 'org1234567;14;dev-feature-team-b;development;deployment;database-proxy',           'development',     'deployment', 'database-proxy',     '{pgbouncer}',                      '2026-02-06 00:00:00+00')
ON CONFLICT DO NOTHING;

SELECT setval('workloads_id_seq', 25);

-- 3. RECOMMENDATION_SETS
-- Each workload's first container gets a recommendation
-- The recommendations JSON follows the Kruize format expected by ros-ocp-backend
INSERT INTO recommendation_sets (id, workload_id, container_name, monitoring_start_time, monitoring_end_time, recommendations, updated_at)
VALUES
  -- prod-data-pipeline: spark-executor (over-provisioned CPU, needs more memory)
  (gen_random_uuid(), 1, 'spark-executor',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 8.0, "format": "cores"}, "memory": {"amount": 17179869184, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0,
         "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 3,
             "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 2.5, "format": "cores"}, "memory": {"amount": 10737418240, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 5.0, "format": "cores"}, "memory": {"amount": 21474836480, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -1.5, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -3.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
             }
           },
           "performance": {
             "pods_count": 3,
             "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 3.5, "format": "cores"}, "memory": {"amount": 12884901888, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 7.0, "format": "cores"}, "memory": {"amount": 25769803776, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.5, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -1.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
             }
           }
         }
       },
       "medium_term": {
         "duration_in_hours": 168.0,
         "monitoring_start_time": "2026-01-30T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 3, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 2.2, "format": "cores"}, "memory": {"amount": 9663676416, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 4.4, "format": "cores"}, "memory": {"amount": 19327352832, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -1.8, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -3.6, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- kafka-streams (well-sized, minor tweaks)
  (gen_random_uuid(), 2, 'kafka-streams',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.8, "format": "cores"}, "memory": {"amount": 3758096384, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 3.6, "format": "cores"}, "memory": {"amount": 7516192768, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.2, "format": "cores"}, "memory": {"amount": -536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.4, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- flink-taskmanager (heavily over-provisioned)
  (gen_random_uuid(), 3, 'flink-taskmanager',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 8.0, "format": "cores"}, "memory": {"amount": 17179869184, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 16.0, "format": "cores"}, "memory": {"amount": 34359738368, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 3.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 6.0, "format": "cores"}, "memory": {"amount": 17179869184, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -5.0, "format": "cores"}, "memory": {"amount": -8589934592, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -10.0, "format": "cores"}, "memory": {"amount": -17179869184, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- prometheus (needs more memory)
  (gen_random_uuid(), 4, 'prometheus',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 0.5, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 1, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.4, "format": "cores"}, "memory": {"amount": 3221225472, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.8, "format": "cores"}, "memory": {"amount": 6442450944, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.1, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.2, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- envoy-proxy (over-provisioned CPU)
  (gen_random_uuid(), 5, 'envoy-proxy',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 8.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 3, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.5, "format": "cores"}, "memory": {"amount": 3221225472, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 3.0, "format": "cores"}, "memory": {"amount": 6442450944, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -2.5, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -5.0, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- rate-limiter
  (gen_random_uuid(), 6, 'rate-limiter',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.3, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.6, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.7, "format": "cores"}, "memory": {"amount": -536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -1.4, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- keycloak
  (gen_random_uuid(), 7, 'keycloak',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.2, "format": "cores"}, "memory": {"amount": 3221225472, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 2.4, "format": "cores"}, "memory": {"amount": 6442450944, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.8, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -1.6, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- product-catalog (us-east)
  (gen_random_uuid(), 8, 'product-catalog',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 3, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -1.0, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -2.0, "format": "cores"}, "memory": {"amount": -4294967296, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- checkout-service
  (gen_random_uuid(), 9, 'checkout-service',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.6, "format": "cores"}, "memory": {"amount": 1610612736, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 1.2, "format": "cores"}, "memory": {"amount": 3221225472, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.4, "format": "cores"}, "memory": {"amount": -536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.8, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- search-engine (us-east) - elasticsearch container
  (gen_random_uuid(), 10, 'elasticsearch',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 8.0, "format": "cores"}, "memory": {"amount": 17179869184, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 3, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 6442450944, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 12884901888, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -2.0, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -4.0, "format": "cores"}, "memory": {"amount": -4294967296, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- product-catalog (eu)
  (gen_random_uuid(), 11, 'product-catalog',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.1, "format": "cores"}, "memory": {"amount": 2684354560, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 2.2, "format": "cores"}, "memory": {"amount": 5368709120, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.9, "format": "cores"}, "memory": {"amount": -1610612736, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -1.8, "format": "cores"}, "memory": {"amount": -3221225472, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- payment-processor (eu)
  (gen_random_uuid(), 12, 'payment-processor',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.5, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.5, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -1.0, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- locust-worker (staging)
  (gen_random_uuid(), 13, 'locust-worker',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 8.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 4, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.5, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 3.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -2.5, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -5.0, "format": "cores"}, "memory": {"amount": -4294967296, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- app-server (staging)
  (gen_random_uuid(), 14, 'app-server',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 2, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.8, "format": "cores"}, "memory": {"amount": 1610612736, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 1.6, "format": "cores"}, "memory": {"amount": 3221225472, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -1.2, "format": "cores"}, "memory": {"amount": -2684354560, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -2.4, "format": "cores"}, "memory": {"amount": -5368709120, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- selenium-runner (qa)
  (gen_random_uuid(), 15, 'selenium-runner',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 4.0, "format": "cores"}, "memory": {"amount": 8589934592, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 5, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -1.0, "format": "cores"}, "memory": {"amount": -2147483648, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -2.0, "format": "cores"}, "memory": {"amount": -4294967296, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- test-orchestrator (qa)
  (gen_random_uuid(), 16, 'test-orchestrator',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 0.5, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 1, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.2, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.4, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.3, "format": "cores"}, "memory": {"amount": -536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.6, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- backend-api (dev-a)
  (gen_random_uuid(), 17, 'backend-api',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 2.0, "format": "cores"}, "memory": {"amount": 4294967296, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 1, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.3, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.6, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.7, "format": "cores"}, "memory": {"amount": -1610612736, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -1.4, "format": "cores"}, "memory": {"amount": -3221225472, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- frontend-app (dev-a)
  (gen_random_uuid(), 18, 'frontend-app',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 0.5, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 1, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.15, "format": "cores"}, "memory": {"amount": 268435456, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.3, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.35, "format": "cores"}, "memory": {"amount": -268435456, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.7, "format": "cores"}, "memory": {"amount": -536870912, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- microservice-a (dev-b)
  (gen_random_uuid(), 19, 'microservice-a',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 0.5, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 1.0, "format": "cores"}, "memory": {"amount": 2147483648, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 1, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.2, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.4, "format": "cores"}, "memory": {"amount": 1073741824, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.3, "format": "cores"}, "memory": {"amount": -536870912, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.6, "format": "cores"}, "memory": {"amount": -1073741824, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00'),

  -- database-proxy (dev-b)
  (gen_random_uuid(), 20, 'pgbouncer',
   '2026-02-01 00:00:00+00', '2026-02-06 00:00:00+00',
   '{
     "current": {
       "requests": {"cpu": {"amount": 0.25, "format": "cores"}, "memory": {"amount": 268435456, "format": "bytes"}},
       "limits":   {"cpu": {"amount": 0.5, "format": "cores"}, "memory": {"amount": 536870912, "format": "bytes"}}
     },
     "recommendation_terms": {
       "short_term": {
         "duration_in_hours": 24.0, "monitoring_start_time": "2026-02-05T00:00:00.000Z",
         "recommendation_engines": {
           "cost": {
             "pods_count": 1, "confidence_level": 0.0,
             "config": {
               "requests": {"cpu": {"amount": 0.1, "format": "cores"}, "memory": {"amount": 134217728, "format": "bytes"}},
               "limits":   {"cpu": {"amount": 0.2, "format": "cores"}, "memory": {"amount": 268435456, "format": "bytes"}}
             },
             "variation": {
               "requests": {"cpu": {"amount": -0.15, "format": "cores"}, "memory": {"amount": -134217728, "format": "bytes"}},
               "limits":   {"cpu": {"amount": -0.3, "format": "cores"}, "memory": {"amount": -268435456, "format": "bytes"}}
             }
           }
         }
       }
     }
   }'::jsonb, '2026-02-06 00:00:00+00')
ON CONFLICT DO NOTHING;

-- VERIFY
SELECT '=== CLUSTERS ===' as info;
SELECT id, cluster_alias, last_reported_at FROM clusters ORDER BY id;

SELECT '=== WORKLOADS ===' as info;
SELECT w.id, c.cluster_alias, w.namespace, w.workload_name, array_length(w.containers, 1) as num_containers
FROM workloads w JOIN clusters c ON w.cluster_id = c.id
ORDER BY w.id;

SELECT '=== RECOMMENDATIONS ===' as info;
SELECT r.container_name, w.workload_name, c.cluster_alias,
       r.monitoring_start_time::date as mon_start,
       r.monitoring_end_time::date as mon_end
FROM recommendation_sets r
JOIN workloads w ON r.workload_id = w.id
JOIN clusters c ON w.cluster_id = c.id
ORDER BY c.cluster_alias, w.workload_name;
