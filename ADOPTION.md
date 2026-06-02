# Adopting the knowledge layer

*A guide for existing delivery teams.*

Most teams that brought AI into their work started with coding, and it paid off there. The gain rarely reached the rest of delivery: requirements, design, testing, deployment, and the work in between barely moved. Work still slows down around the coding: a requirement that was never written down clearly, a decision no one remembered, a handoff that loses context along the way. Faster coding only takes you so far when the phases around it don't have what they need written down anywhere.

A knowledge layer gives the whole team, people and agents alike, one shared place to read from and write to. Decisions, specs, and policies live there as written documents, and they're the source of truth for everyone working on the project. This guide is about how a team makes that move, from code-first to context-first. The technical setup is a separate task a developer handles; what follows is the change in how people work, which is what decides whether the practice lasts. Treat it as one workable setup rather than the only one; it's a starting point, and teams are expected to adapt it to their context.

## The document comes first

The writing comes first and the code follows. A change begins as a written document, reviewed in a pull request the same way a code change is, and only then is it built. The documents are treated like code: they're kept in version control, reviewed and merged the same way, and carry the same history, so the corpus has the discipline the codebase already has. Because each one is written down, with its dependencies noted, an agent can build from it and the team can check the result against it.

This is more than keeping documentation. Documentation usually comes after the code, falls behind it, and stops being trusted. Here the document is written first and is what the team reviews and agrees on. For that to hold, writing has to be part of doing the work, not a separate task that can be put off. Once it's optional, people stop doing it.

## Start small

There's no need to change everything at once. Pick one kind of work where writing first clearly helps, and let the team see it help before you ask them to do more.

A few good places to begin:

- **Decisions.** Write down the decisions the team makes. This isn't about freezing them; decisions change for good reasons, and when one does, the earlier version stays on record. It's so that people can see what has already been decided instead of guessing or unknowingly contradicting it.
- **Specs.** Write the spec before building, let an agent build from it, and see how the rework compares to before.
- **A risky change.** Take a change that could affect things elsewhere, write it down with what it depends on, and check the impact before touching any code.

Run one of these until it feels normal, then widen it.

## The habits that make it stick

The way of working comes down to three habits.

- **Write before you build.** The document is part of getting the change merged, reviewed alongside the code rather than after it. When it isn't required to merge, people skip writing it.
- **Check before you change.** Before touching settled work, look up the current decision and what depends on the thing you're about to change, so you don't contradict something you didn't know was there.
- **Clear drift each week.** Set aside a short, regular slot to fix anything that's out of date or now contradicts something else. Doing this every week keeps the corpus current. If it's left too long, people stop trusting what's in it.

## What changes for each role

The change is small for any one person.

- The **product manager or product owner** writes the decision or spec first, rather than explaining it in a meeting, and checks whether a decision already exists before opening it again.
- The **business analyst** writes requirements as documents the rest of the work builds on, instead of leaving them in tickets and threads.
- The **architect** records the significant technical decisions and constraints, so everyone building against them can see them.
- The **designer** records the settled voice, patterns, and constraints once, instead of explaining them again in every review.
- The **engineer** reads the spec and what it depends on before building, or has an agent build from it, and checks the impact before changing settled work.
- **QA** keeps test patterns in the corpus and checks the work against the spec, which now exists in its own right.
- **DevOps and SRE** keep runbooks and operational decisions in the corpus, and look there first when something breaks.
- **Security and compliance** keep the policies there, the rules for what can and can't happen, and check work against them before sign-off.

New joiners benefit the most, since a lot of what they'd need to learn is already written down.

## Who keeps it running

One person should own the corpus itself, apart from owning any single document. Teams name this role differently, knowledge owner, content curator, or context engineer; the label matters less than someone clearly holding it. They keep the document standards current, make sure the weekly cleanup actually happens, help people who aren't sure how to write something down, and watch for the corpus drifting out of date. On a small team one person can hold it alongside their other work; on a larger one it's worth making it someone's explicit responsibility. Without a clear owner, the standards slip and the cleanup stops happening.

## Beyond the delivery team

The corpus isn't only for the people building. Anyone connected to it through MCP can ask a question and get an answer from the knowledge layer. A founder can check what the team has committed to before a customer call, legal or compliance can check a policy, marketing can check what's safe to claim. They don't have to write documents or learn the standards; they just ask, and the same source of truth answers everyone.

## What it gives you

Working this way gives the team a few things it didn't have before. Answers come from the team's own documents, with their source and status attached, so an agent isn't filling gaps with guesses. Before changing something settled, you can see what depends on it. The layer flags its own drift, the places where documents have gone out of date or started to disagree. And the knowledge stays put when people move on, rather than leaving with them.

## Rolling it out

You don't need a big launch. Start by putting in the document standards and a few real documents, the decisions the team already argues about and one live spec, without going back to write up old work. Choose the one stream you'll begin with and the one thing you'll measure.

Then run that stream the new way: the document is needed to merge, agents build from the specs, and the weekly cleanup starts even while there's little to clean, so the habit forms early.

Once it's steady, bring in the phases next to it, and try it on onboarding by handing a new person the corpus and seeing how quickly they become productive. Compare your measure against where it started. From there the benefit grows: the more that gets written down, the more the corpus can answer, and finding out what a change will affect is a quick lookup rather than a guess.

## What to measure

Pick one or two measures, and take a reading before you start so you have something to compare against. The ones worth watching:

- **Cycle time**, from idea to merged, which shows the friction sitting between phases.
- **Rework**, how often finished work comes back because the spec was wrong or missing.
- **Ramp time**, how long a new person takes to get productive.
- **Rework from contradicted decisions**, work redone because it went against something already decided.

Counting documents or lines of code measures activity rather than delivery, so leave those aside.

## Where to start

The way of working is the same whatever brought the team to it; only the first step and the measure change with the problem.

| If the problem is... | Begin with... | Measure... |
|---|---|---|
| Coding gains not reaching delivery | Specs written first | Cycle time, rework |
| Work that contradicts past decisions | The decisions log | Rework from contradicted decisions |
| Slow ramp, or knowledge leaving with people | Seeded decisions and an onboarding test | Ramp time |
| Changes that break unrelated things | A risky change | Escaped defects, change failure rate |
| Agents producing plausible but wrong work | Specs an agent builds from | Work accepted without major rework |

## How it goes wrong

A few failures are common enough to plan for. Asking everyone to write specs from day one gets you specs written to satisfy a rule rather than to help, so start with one stream instead. If writing the document isn't required before the code can merge, people skip it, so make it a requirement. If no one owns the weekly cleanup, the corpus fills with stale claims, so give it a named owner.

## Signs it's working

You'll notice it before any measure moves. People answer "what did we decide about this" with a lookup rather than a question in chat. Pull requests arrive with the spec already written, without anyone asking. A new person starts contributing without booking time with half the team. People query the knowledge layer before a meeting, and the meeting is shorter for it. When that's simply how the team works, the gains the team got from coding start to reach the rest of delivery.
