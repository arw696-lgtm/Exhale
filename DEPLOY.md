# Exhale — Go-Live Guide

*Andy — this is the whole path from "it's in a repo" to "it's quietly reading
my real inbox on a Tuesday." Written for you to follow one evening, in order.
Nothing here needs to be memorized; just do the steps top to bottom.*

**What you need before you start:**
- A domain name you control (e.g. `exhale.thewards.space` — a subdomain of
  something you already own is perfect, and free).
- A small server — a $6–12/month VPS (DigitalOcean, Hetzner, Linode all work).
  You do **not** need anything powerful; this is a household, not a startup.
- About an evening. The one genuinely fiddly part is the Google registration
  (Step 4), and this guide clicks through it with you.

**What only you can do, and why:** the server, the domain, the Google
registration, and the API key are all tied to *your* accounts and *your* card.
I can't do those for you — but everything below is paint-by-numbers so there's
no guessing.

---

## Step 1 — Get a server

1. Create a VPS with **Ubuntu 24.04**. On DigitalOcean this is "Create → Droplet
   → Ubuntu → the $6/mo basic size."
   - For authentication choose **SSH key**, not a password. If you don't have
     one, run `ssh-keygen -t ed25519 -C "exhale"` on your laptop, then
     `cat ~/.ssh/id_ed25519.pub` and paste that line (the one starting
     `ssh-ed25519`) into DigitalOcean. The file *without* `.pub` is the private
     half — it never leaves your laptop.
   - Afterwards, in the droplet's settings, enable **Backups** (+$1.20/mo).
     That is your off-box copy of everything except the master secret.
2. Note its **public IP address** (e.g. `203.0.113.42`).
3. SSH in from your laptop's terminal: `ssh root@203.0.113.42`
4. Install Docker (one command, paste it in):
   ```sh
   curl -fsSL https://get.docker.com | sh
   ```
   That's the whole server setup. Docker runs everything else.

## Step 2 — Point your domain at the server

In your domain registrar's DNS settings, add one record:

| Type | Name | Value |
|------|------|-------|
| A | `exhale` (or whatever subdomain you want) | your server IP |

So `exhale.thewards.space → 203.0.113.42`. DNS can take a few minutes to an hour
to propagate — you can keep going while it does.

## Step 3 — Get the code and set your secrets

On the server:

```sh
git clone https://github.com/arw696-lgtm/Exhale.git
cd Exhale
cp .env.example .env
```

One command generates all three secrets, sets the production posture (auth
on, invite-only, hourly sync), and prints what you need to save:

```sh
./scripts/setup-env.sh exhale.thewards.space you@yourname.com
```

It refuses to overwrite an existing `.env` — deliberately. Generating a new
master secret against a database encrypted under the old one locks every
family out of their own data.

*(Prefer doing it by hand? `cp .env.example .env`, then `nano .env` and fill
in `EXHALE_DOMAIN`, `EXHALE_TLS_EMAIL`, `POSTGRES_PASSWORD`,
`EXHALE_MASTER_SECRET`, and `EXHALE_BOOTSTRAP_INVITE`. Generate each secret
with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.)*

> **⚠️ The master secret is the one thing you can never lose.** It's what
> decrypts every family's data, and it is deliberately *not* stored in the
> database. Put it in your password manager right now. Lose it and the data is
> unrecoverable by design — that's the whole point of the zero-knowledge
> design, and it cuts both ways.

You can launch now and add Google/API-key later, or fill those in first
(Steps 4–6). Either works — Exhale runs fine before they're set; those
features just stay dark until they are.

## Step 4 — Register the "Connect Google" app (the fiddly one)

This is a one-time thing that lets *anyone* in your family click "Connect
Google" and hand Exhale read access to their own Gmail + Calendar. Take it slow;
it's clicky but not hard.

1. Go to **console.cloud.google.com** and create a project (top bar → "Select a
   project" → "New Project" → name it "Exhale").
2. **Enable the APIs** you'll use: search bar → "Gmail API" → Enable. Then again
   for "Google Calendar API" → Enable.
3. **OAuth consent screen** (left menu → "APIs & Services" → "OAuth consent
   screen"):
   - User type: **External**. (This just means "not a Google Workspace org." It
     stays private to whoever you hand the app to.)
   - App name "Exhale", your email as support + developer contact. Save.
   - **Scopes**: add `.../auth/gmail.readonly` and `.../auth/calendar.events`
     and `.../auth/calendar.readonly`. (You can also just add them later.)
     That trio is the whole permission story: read mail, read calendars, write
     calendar *events* — never send mail, never delete a calendar.
   - **Publish the app.** Click **"Publish app"** so its status is *In
     production*, not *Testing*.

     > ⚠️ **This step is not optional for a set-it-and-forget-it household.**
     > In *Testing* mode Google expires every refresh token after **7 days** —
     > Exhale would silently lose access to Gmail once a week, forever. In
     > production the tokens persist.
     >
     > The tradeoff: because Gmail is a "restricted" scope and you aren't going
     > through Google's formal verification review (that process is for
     > companies shipping to strangers), you and Ali will each see a
     > **"Google hasn't verified this app"** warning the *first* time you
     > connect. Click **Advanced → Go to Exhale (unsafe)**. It says "unsafe"
     > because Google can't vouch for the developer — the developer is you.
     > One click each, once.
4. **Create the credential** (left menu → "Credentials" → "Create Credentials"
   → "OAuth client ID"):
   - Application type: **Web application**.
   - Authorized redirect URI — paste exactly this, with your domain:
     ```
     https://exhale.thewards.space/v1/oauth/google/callback
     ```
   - Create. Google shows you a **Client ID** and **Client Secret**.
5. Put them in `.env`:
   ```
   EXHALE_GOOGLE_CLIENT_ID=(the client id)
   EXHALE_GOOGLE_CLIENT_SECRET=(the client secret)
   EXHALE_GOOGLE_REDIRECT_URI=https://exhale.thewards.space/v1/oauth/google/callback
   ```

That's the hard part done. (Outlook is the same shape via Azure if you ever want
it — `EXHALE_MSFT_*`, redirect ending `/v1/oauth/microsoft/callback` — but skip
it unless someone actually uses Outlook.)

## Step 5 — Anthropic API key (5 minutes)

This powers reading the emails and photos that plain rules can't. Go to
**console.anthropic.com** → API Keys → Create Key. Put it in `.env`:

```
ANTHROPIC_API_KEY=(the key)
```

(Leave `EXHALE_LLM_EXTRACTOR=1` — the prod file already defaults it on.)

## Step 6 — Alert emails (optional, 5 minutes)

So 🔴 critical items can reach you by email. Any SMTP works — a Gmail
"app password", or Mailgun/Postmark free tier. In `.env`:

```
EXHALE_SMTP_HOST=smtp.gmail.com
EXHALE_SMTP_USER=you@gmail.com
EXHALE_SMTP_PASSWORD=(a Gmail app password, not your login)
EXHALE_SMTP_FROM=you@gmail.com
```

Skip this for launch if you want; you'll just check the briefing yourself until
it's set.

## Step 7 — Launch

```sh
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes a few minutes. Then visit **https://exhale.thewards.space** —
Caddy will have fetched a real HTTPS certificate automatically (if it hasn't
yet, wait for DNS from Step 2 and reload). You should see the Exhale sign-in.

Check it's healthy any time with:
```sh
docker compose -f docker-compose.prod.yml ps        # all "running"
docker compose -f docker-compose.prod.yml logs -f api   # live backend logs
```

## Step 8 — Create your account and go live

1. On the sign-in screen, **sign up**. Because signups are invite-only in
   production, use your `EXHALE_BOOTSTRAP_INVITE` code as the invite code — that
   mints *your* family and makes you a full member.
2. Click **Connect Google**, sign in as yourself, approve. Within a few minutes
   the background sync starts its 180-day retro scan of your real Gmail, and the
   briefing begins filling with *your* obligations.
3. **Invite Ali**: your family invite code is shown in the app (top of the
   briefing). She signs up with *that* code (not the bootstrap one) → she joins
   your family as a full equal, connects her own Google, and now both your
   inboxes and calendars feed the same brain. (This is exactly what the
   per-member connection work was for — neither of you displaces the other.)
4. Set up the household: the coverage model (kids, caregivers, schools), or snap
   a school-calendar photo. Publish the shared iCloud calendar and paste its
   `.ics` URL if you want those events in too.

Then live with it for two weeks. That's the actual test.

## Day-to-day

- **Backups** run nightly on their own into a Docker volume. To copy one off the
  server: `docker compose -f docker-compose.prod.yml cp backup:/backups ./backups`.
  Remember a backup is useless without `EXHALE_MASTER_SECRET` — keep that safe
  separately.
- **Update to the latest code:**
  ```sh
  git pull
  docker compose -f docker-compose.prod.yml up -d --build
  ```
  Your data lives in Docker volumes and survives rebuilds.
- **Restart everything:** `docker compose -f docker-compose.prod.yml restart`
- **Stop:** `docker compose -f docker-compose.prod.yml down` (data persists).

## If something's off

- **Site won't load / no certificate:** DNS probably hasn't propagated, or the
  A record is wrong. Check `docker compose -f docker-compose.prod.yml logs caddy`
  — it says plainly if it couldn't get a cert for the domain.
- **"Connect Google" says not configured:** the `EXHALE_GOOGLE_*` vars aren't
  set, or you changed `.env` without a restart. Re-run the `up -d` command.
- **Google "redirect_uri_mismatch":** the redirect URI in Step 4 must match
  `EXHALE_GOOGLE_REDIRECT_URI` *exactly*, including `https://` and no trailing
  slash.
- **Briefing stays empty after connecting:** the retro scan runs on the
  auto-sync cycle (hourly by default). Give it an hour, or watch `logs -f api`.

---

*Everything in this guide targets `docker-compose.prod.yml`. The plain
`docker-compose.yml` is for running it on your laptop with no domain — same app,
no HTTPS, `http://localhost:8080`.*
