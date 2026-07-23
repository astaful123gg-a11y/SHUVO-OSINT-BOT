const mineflayer = require('mineflayer');

const args     = process.argv.slice(2);
const host     = args[0] || 'localhost';
const port     = parseInt(args[1]) || 25565;
const username = args[2] || 'SHUVO_BOT';
const password = args[3] || 'ShuvoBot@2024';

let bot            = null;
let loginSent      = false;
let afkTimer       = null;
let reconnectTimer = null;
let manualStop     = false;
let reconnectDelay = 15000;  // starts at 15s, backs off on repeated failures
let failCount      = 0;

function log(msg) {
    process.stdout.write(msg + '\n');
}

// ── Send login/register to server ──
function doLogin() {
    if (loginSent || !bot) return;
    loginSent = true;
    log('STATUS:logging_in');
    setTimeout(() => {
        try { bot.chat('/register ' + password + ' ' + password); } catch (e) {}
    }, 600);
    setTimeout(() => {
        try { bot.chat('/login ' + password); } catch (e) {}
        setTimeout(() => { log('STATUS:logged_in'); }, 500);
    }, 1500);
}

// ── Anti-AFK: look around + brief step every 20s ──
function startAntiAfk() {
    stopAntiAfk();
    afkTimer = setInterval(() => {
        if (!bot || !bot.entity) return;
        try {
            // Rotate yaw randomly to simulate looking around
            const yaw   = bot.entity.yaw + (Math.random() - 0.5) * 1.2;
            const pitch = (Math.random() - 0.5) * 0.6;
            bot.look(yaw, pitch, false);
            // Short forward movement
            bot.setControlState('forward', true);
            setTimeout(() => {
                try {
                    if (bot) bot.setControlState('forward', false);
                } catch (e) {}
            }, 600);
        } catch (e) {}
    }, 20000);
}

function stopAntiAfk() {
    if (afkTimer) { clearInterval(afkTimer); afkTimer = null; }
}

// ── Schedule a reconnect ──
function scheduleReconnect() {
    if (manualStop) return;
    if (reconnectTimer) return;
    const delay = reconnectDelay;
    log('STATUS:reconnect_in_' + Math.round(delay / 1000) + 's');
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (!manualStop) createBot();
    }, delay);
    // Exponential backoff, cap at 60s
    reconnectDelay = Math.min(reconnectDelay * 1.5, 60000);
}

// ── Main bot creation ──
function createBot() {
    if (manualStop) return;
    loginSent = false;
    stopAntiAfk();
    bot = null;
    log('STATUS:connecting');

    let b;
    try {
        b = mineflayer.createBot({
            host:                  host,
            port:                  port,
            username:              username,
            auth:                  'offline',
            version:               '1.21.4',
            hideErrors:            true,
            checkTimeoutInterval:  30000,
            physicsEnabled:        true,
        });
    } catch (e) {
        log('STATUS:error:' + String(e).slice(0, 120));
        scheduleReconnect();
        return;
    }

    bot = b;

    // ── Spawned in world ──
    b.once('spawn', () => {
        failCount = 0;
        reconnectDelay = 15000;  // reset backoff on success
        log('STATUS:online');
        log('JOINED:' + username);
        startAntiAfk();

        // Proactively try login after 2s (some servers need you to login on join)
        setTimeout(() => {
            if (!loginSent) doLogin();
        }, 2000);
    });

    // ── Chat login prompts ──
    b.on('chat', (_sender, message) => {
        const m = message.toLowerCase();
        if (!loginSent && (
            m.includes('login') || m.includes('register') ||
            m.includes('authme') || m.includes('please log')
        )) {
            doLogin();
        }
    });

    // ── System/server messages (ActionBar, title, etc.) ──
    b.on('message', (jsonMsg) => {
        const m = jsonMsg.toString().toLowerCase();
        if (!loginSent && (
            m.includes('login') || m.includes('register') || m.includes('authme')
        )) {
            doLogin();
        }
    });

    // ── Kicked — detect login-required kicks ──
    b.on('kicked', (reason) => {
        stopAntiAfk();
        const r = String(reason).toLowerCase();
        log('STATUS:kicked:' + String(reason).slice(0, 120));
        // If kicked because login was required, retry immediately after reconnect
        if (r.includes('login') || r.includes('auth')) {
            loginSent = false;
        }
        scheduleReconnect();
    });

    // ── Death — respawn automatically ──
    b.on('death', () => {
        log('STATUS:died_respawning');
        try { b.respawn(); } catch (e) {}
    });

    // ── Generic error ──
    b.on('error', (err) => {
        stopAntiAfk();
        log('STATUS:error:' + String(err.message || err).slice(0, 120));
        // Don't call scheduleReconnect here — 'end' always fires after 'error'
    });

    // ── Connection ended ──
    b.on('end', (reason) => {
        stopAntiAfk();
        bot = null;
        log('STATUS:disconnected:' + (reason || ''));
        if (!manualStop) {
            failCount++;
            scheduleReconnect();
        }
    });
}

// ── Stdin commands from Python ──
process.stdin.setEncoding('utf8');
process.stdin.on('data', (raw) => {
    const cmd = raw.trim();
    if (cmd === 'stop') {
        manualStop = true;
        log('STATUS:stopping');
        stopAntiAfk();
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        if (bot) { try { bot.quit('Bot stopped by user'); } catch (e) {} bot = null; }
        setTimeout(() => process.exit(0), 500);

    } else if (cmd === 'rejoin') {
        manualStop = false;
        loginSent  = false;
        reconnectDelay = 15000;
        log('STATUS:rejoining');
        stopAntiAfk();
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        if (bot) { try { bot.quit('Rejoining'); } catch (e) {} bot = null; }
        setTimeout(createBot, 2000);
    }
});

process.on('SIGTERM', () => {
    manualStop = true;
    stopAntiAfk();
    if (bot) { try { bot.quit(); } catch (e) {} }
    process.exit(0);
});

// ── Boot ──
createBot();
