const { execFileSync } = require('child_process');

const ports = [8080, 3000, 8000, 8001];

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function getListeningPidsWindows(targetPorts) {
  const output = execFileSync('netstat', ['-ano', '-p', 'tcp'], { encoding: 'utf8' });
  const pids = [];

  for (const line of output.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.includes('LISTENING')) continue;

    const parts = trimmed.split(/\s+/);
    if (parts.length < 5) continue;

    const localAddress = parts[1];
    const pid = parts[4];
    const match = localAddress.match(/:(\d+)$/);
    if (!match) continue;

    const port = Number(match[1]);
    if (targetPorts.includes(port)) {
      pids.push(pid);
    }
  }

  return unique(pids);
}

function stopProcessWindows(pid) {
  try {
    execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
    console.log(`[predev] stopped PID ${pid}`);
  } catch {
    // Ignore failures so one stubborn process does not block the whole dev start.
  }
}

function main() {
  if (process.platform !== 'win32') {
    console.log('[predev] non-Windows platform detected; skipping automatic port cleanup');
    return;
  }

  let pids = [];
  try {
    pids = getListeningPidsWindows(ports);
  } catch (err) {
    console.warn(`[predev] unable to inspect listening ports: ${err.message}`);
    return;
  }

  if (!pids.length) {
    console.log('[predev] no stale dev listeners found');
    return;
  }

  console.log(`[predev] stopping stale listeners on ports ${ports.join(', ')}`);
  pids.forEach(stopProcessWindows);
}

main();