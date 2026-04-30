# Architecture Decision Record

A single-page record of the load-bearing decisions behind Hardball. Each section answers "why this and not the other reasonable thing" in 2–3 sentences.

## Why Flask, not FastAPI

Flask is the framework I have the most reps with, and the API surface is small enough (four routes, one upstream call) that async I/O wouldn't move the needle. FastAPI's strengths — Pydantic validation, OpenAPI generation, native async — would be over-engineering for a portfolio project, and Flask + Gunicorn has the simpler deploy story on Elastic Beanstalk's Python platform.

## Why Elastic Beanstalk, not ECS or Lambda

EB has the lowest config overhead for a single-container Python WSGI app — a Procfile and `requirements.txt` is the entire spec. ECS would add a Dockerfile, a task definition, and an ALB to think about for no benefit at this size, and Lambda's cold-start + 6 MB request/response cap is a poor fit for an LLM proxy that streams multi-second responses. EB is the boring right answer.

## Why a CloudFront `/api/*` proxy, not direct HTTPS on EB

Putting HTTPS directly on the EB endpoint requires an Application Load Balancer plus an ACM certificate plus a custom domain — about $18/mo of load balancer plus DNS work. Routing `/api/*` through CloudFront is free under the existing distribution, gives the API a TLS-terminated edge for nothing, and as a bonus collapses the frontend and backend into the same origin from the browser's perspective.

## Why same-origin `/api/*`, not CORS

Same-origin eliminates an entire class of bugs: no preflight `OPTIONS`, no `Access-Control-Allow-Origin` mismatches, no credentials/cookies edge cases, no surprises when an SDK adds a new header. CORS is still configured on the backend for local dev (frontend on `:5173`, backend on `:5000`), but production never exercises that path.

## Why request-time `os.environ.get`, not a module-level constant

The chat handler reads `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` on every request. That means `eb setenv` updates take effect on the next request without restarting workers — important during the Sprint 3 debugging when the model id was changing every few minutes. A module-level constant would have required a Gunicorn reload after each `setenv`, slowing the feedback loop and creating one more thing to forget.
