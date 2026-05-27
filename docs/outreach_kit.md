# NGO outreach kit — one practitioner voice in the demo video

The single highest-leverage thing left before the deadline is getting **one
30-minute conversation with a practitioner from the reunification field** and
quoting them on-screen in the demo. This file is the kit for doing that.

**Goal:** one paragraph + permission to quote, on screen at 2:30 of the demo
video. Even an attributed-by-role-only quote ("a former FEMA Family
Assistance Center coordinator") moves the credibility needle.

**Lead time:** 2 weeks is realistic. Cold-email response rates in disaster
response orgs are 15–25% based on the public footprint of these programs.
Send 6–8 emails to land 1–2 calls.

---

## Target list (ranked by reach × likelihood-of-response)

### Tier 1 — most likely to engage with a student/hackathon project
1. **Local Red Cross chapter — Houston / Greater Houston Region**
   - Public contact: https://www.redcross.org/local/texas/gulf-coast.html
   - Ask for: volunteer coordinator (not the comms team — they'll bounce you)
   - Why they'll engage: Houston is a recurring disaster geography and they
     run periodic comms drills. Volunteer coordinators usually have
     mass-care experience and time to answer.
   - Best question for them: *"What goes wrong with reunification matching
     when Spanish-speaking and Vietnamese-speaking families show up at the
     same shelter?"*

2. **Mass Care Strategy National Listserv (community of practice)**
   - https://nationalmasscarestrategy.wordpress.com/
   - This is a working group of ARC + FEMA + NCMEC + state EM staff. The
     blog has named contributor names you can search on LinkedIn.
   - Why they'll engage: practitioner-to-practitioner sharing culture.
   - Best question for them: *"Where in the NSS data-flow does a multilingual
     fuzzy matcher even slot in — before or after intake to NSS?"*

3. **Former FEMA Family Assistance Center alums on LinkedIn**
   - LinkedIn search: `"Family Assistance Center" "FEMA"` filter by
     "people" and "United States." Pull a list of ~15. Most have moved on
     to private-sector emergency management.
   - Why they'll engage: they've seen exactly this problem and few people
     ever ask them about it.
   - Best question: *"If a tool like this had existed during [the disaster
     they worked], what's the one thing it would have had to do?"*

### Tier 2 — strong fit, harder to reach
4. **NCMEC Communications team** (umbrella for the Unaccompanied Minors
   Registry — UMR) · https://www.missingkids.org/footer/about/contact
   - Tell them up front you are NOT trying to compete with NCMEC UMR —
     DisasterLens hands minors OFF to them (this is in the README and the
     Coordinator prompt's safety rule #8).
   - Best question: *"What does a healthy 'hand-off' from a private
     reunification tool to UMR look like in your view?"*

5. **ICRC — Restoring Family Links communications**
   - https://www.icrc.org/en/contact
   - Lower probability of engaging — ICRC is operational not promotional —
     but if they DO respond, you have the strongest possible voice in the
     video. Position the project as "complementary to Trace the Face,
     useful for in-country shelter-roster cases where ICRC isn't the
     right tool."

6. **University disaster-research labs**
   - U. of Delaware Disaster Research Center · https://www.drc.udel.edu/
   - U. of North Texas Center for Public Service · contact via dept page
   - Why: PhD students working on these topics need real-world artifacts to
     analyze and will often quote in exchange for early access. Lowest
     pressure of any audience here.

### Tier 3 — adjacent, lower priority for a quote, useful for context
7. SAMHSA Disaster Distress Helpline — multilingual phone helpline; not a
   reunification operator but knows the multilingual-crisis primitive.
8. United Way 211 chapters — operates disaster recovery information lines.
9. Local Houston-area church / mosque / community center networks that
   played a coordination role in Harvey (2017) or Beryl (2024).

---

## Email template — short, specific, no-ask version

Subject: *3-minute video on multilingual disaster reunification — 30 min for your read?*

Hi [Name],

I'm building a senior project on multilingual family reunification after
disasters (specifically the case where shelter intake captures a name in
the wrong script — Spanish in one shelter, Vietnamese in another, Arabic
in a third). The system is an AI agent that searches the shelter rosters
across spelling/script variants, but every match goes through a human
verifier and the agent never disclose s the location of a minor without
explicit guardian verification.

Submission is on **June 11, 2026**, to the Google Cloud Rapid Agent
Hackathon. I want to make sure I'm not building something that solves a
problem only I can see.

Could you spare **30 minutes** in the next two weeks to watch a 3-minute
walk-through and tell me what's wrong with it? I'll send a calendar link.

Not asking you to endorse anything — just looking for your read. If you
have any reaction worth quoting, even anonymously by role ("a former FEMA
Family Assistance Center coordinator"), that would mean a lot.

— Saurabh
[contact info]

---

## Calendar / video logistics

- 30-minute Google Meet or Zoom — give them options
- Have the 3-minute demo video ready to share screen
- Record the conversation only if they explicitly consent (most won't)
- Take written notes; you only need 1–3 sentences worth of quote material
- **Get permission to quote in writing** (email reply is fine): "Is it OK
  to include the line *'...'* in the video, attributed to *[role only]* /
  *[name + role]*?"

---

## What to ask in the call

The four questions that produce the most usable quotes, in priority order:

1. *"What's the moment in a real reunification case where existing tools
   feel inadequate?"* — produces a vivid story you can quote.
2. *"What would you NOT want a tool like this to do?"* — produces a
   safety/scope quote that turns the demo's verifier-gate into a feature
   the practitioner endorsed.
3. *"Have you ever seen a case where someone was reunified with the
   wrong person? What happened?"* — answers usually become the "this is
   why we have the verifier gate" beat.
4. *"If you had to pick one capability to add to Safe and Well, what would
   it be?"* — this often produces an exact match for what DisasterLens
   already does, which is the most credibility-multiplying quote possible.

Avoid:
- Pitching your tool. They'll tune out.
- Asking "would you use this?" — they won't commit.
- Asking technical questions about Elastic, GCP, ADK. Wrong audience.

---

## What to do with the quote

In the video, around 2:30, render the quote as text-on-screen over a
muted shot of the verifier UI in action. Source line below in smaller text:
*— [Name, role, organisation]* or *— [Role only], used with permission*.

Also add the quote to README.md under a new "## What practitioners say"
section directly above "## Measured Performance," with the same
attribution. Judges who look at the repo as well as the video will see it
in both places, which compounds the credibility lift.

---

## Failure modes and fallbacks

**If nobody responds in 2 weeks:** Re-send the email with a tighter ask —
"could you reply with one sentence on what you'd want from a tool like
this?" 1-line email replies are far easier to get than 30-min calls and
often work as quotes.

**If the only voice you can get is academic, not operational:** Use them
anyway. An attributed quote from a disaster-research professor is still
worth more than zero practitioner voice.

**If you get a quote that's lukewarm or critical:** Quote it anyway, and
add a line in the README saying what you changed in response. "We adjusted
the minor-disclosure flow after [person] flagged the guardian-verification
step as too easy to skip." A self-aware concession in the video signals
maturity and is usually rewarded by judges.
