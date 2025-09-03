const path = require('path');
const express = require('express');
const bodyParser = require('body-parser');
const jwt = require('jsonwebtoken');
const { spawn } = require('child_process');
const fs = require('fs');

// Load .env from repo root
const rootDir = path.join(__dirname, '..');
const envPath = path.join(rootDir, '.env');
if (fs.existsSync(envPath)) {
  require('dotenv').config({ path: envPath, override: true });
}

const app = express();
const port = process.env.UI_PORT || 3001;

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

app.get('/health', (_req, res) => res.send('OK'));

app.get(['/', '/simulate'], (_req, res) => {
  res.render('simulate', {
    title: 'Agent2 Simulator',
    livekitUrl: process.env.LIVEKIT_URL || '',
  });
});

let agentProc = null;
let agentInfo = { lang: null };

function startAgent(agentToken, langCode) {
  if (agentProc && !agentProc.killed) {
    try { agentProc.kill('SIGTERM'); } catch (_) {}
  }
  const cmd = `cd ${rootDir} && $(command -v uv) run --env-file .env python -m src.agent --lang ${langCode || 'en'}`;
  const env = { ...process.env, AGENT_ROOM_TOKEN: agentToken };
  agentProc = spawn('/bin/bash', ['-lc', cmd], { stdio: 'inherit', env });
  agentInfo.lang = langCode || 'en';
  agentProc.on('exit', () => { agentProc = null; agentInfo.lang = null; });
}

app.get('/api/agent/status', (_req, res) => {
  const running = !!agentProc && !agentProc.killed;
  res.json({ running, lang: agentInfo.lang });
});

app.post('/api/agent/stop', (_req, res) => {
  try {
    if (agentProc && !agentProc.killed) {
      agentProc.kill('SIGTERM');
      agentProc = null;
      return res.json({ ok: true, stopped: true });
    }
    return res.json({ ok: true, stopped: false });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e?.message || e) });
  }
});

app.post('/api/simulate/start', (req, res) => {
  try {
    const roomName = req.body.room || 'dev';
    const langCode = (req.body.lang || 'en').toLowerCase();
    const identity = `tester-${Math.random().toString(36).slice(2, 10)}`;

    const apiKey = process.env.LIVEKIT_API_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET;
    const lkUrl = process.env.LIVEKIT_URL;
    if (!apiKey || !apiSecret || !lkUrl) {
      return res.status(500).json({ error: 'LIVEKIT_URL/API_KEY/API_SECRET are required' });
    }
    const now = Math.floor(Date.now() / 1000);
    const agentPayload = {
      iss: apiKey,
      sub: `agent-${Math.random().toString(36).slice(2, 8)}`,
      iat: now,
      exp: now + 3600,
      nbf: now - 10,
      video: { roomJoin: true, room: roomName, canPublish: true, canSubscribe: true },
    };
    const browserPayload = {
      iss: apiKey,
      sub: identity,
      iat: now,
      exp: now + 3600,
      nbf: now - 10,
      video: { roomJoin: true, room: roomName, canPublish: true, canSubscribe: true },
    };
    const agentToken = jwt.sign(agentPayload, apiSecret, { algorithm: 'HS256', header: { kid: apiKey } });
    const token = jwt.sign(browserPayload, apiSecret, { algorithm: 'HS256', header: { kid: apiKey } });

    startAgent(agentToken, langCode);
    res.json({ ok: true, token, room: roomName, url: lkUrl, identity });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Failed to start' });
  }
});

app.listen(port, () => {
  console.log(`UI listening on http://localhost:${port}`);
});

