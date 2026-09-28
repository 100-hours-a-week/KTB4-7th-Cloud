# SSE response buffering reproduction contract

## Expected behavior

For browser chat responses at `POST /v1/chat/messages` and AI responses at
`POST /internal/v1/ai/chat/messages`, Nginx forwards upstream response chunks
without waiting to buffer the complete response. Other paths keep their current
proxy behavior.

## Reproduction / regression command

Run from the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The regression contract checks each exact chat location for
`proxy_buffering off;` and verifies it continues to proxy to `app_upstream`.

## Baseline observation

Both `deploy/backend/nginx/nginx.conf` and `deploy/ai/nginx/nginx.conf` currently
send chat requests through the general `location /` block, which has no
`proxy_buffering off;`. Nginx therefore uses its default response buffering.
The report also identifies the public `api.memme.kr` Nginx as the response hop
to the browser. AI Compose also mounted the tracked config file directly, while
the deployment script only copied Backend config to a stable runtime file;
after a Git checkout, the running AI Nginx could retain the old bind-mounted
inode and miss the config change.

## Success criteria

- Both chat paths have dedicated locations with response buffering disabled.
- AI deploy uses the same stable runtime Nginx config mount strategy as Backend,
  and refreshes the runtime file before bringing up/reloading Nginx.
- The new configuration contract passes.
- Existing backend CORS preflight and response headers remain configured.
- Nginx syntax validation passes if an Nginx runtime is available.
