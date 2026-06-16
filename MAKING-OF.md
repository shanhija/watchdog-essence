# The prompts behind the Watchdog Essence

This is the sequence of prompts that produced [`ESSENCE.md`](ESSENCE.md) and this two-context demo
repo — shared in the spirit of the project itself: *the prompts are the spec.* They're reproduced
verbatim (typos and all); the short *italic notes* say what each step changed.

The work started from a real, internal `devops-watchdog` service (logs → triage → auto-fix → PR).
The ask evolved from "explain it" → "distill it into a vendor-neutral spec" → "make a repo where
anyone can hand that spec to an AI and watch it rebuild the system in their own stack." (There was a
companion build-in-public blog post in parallel; those prompts are left out here to keep this focused
on the essence.)

---

## 0. Understand the system

> please read through the watchdog and produce here a list of "how it works"

*Read the real service and produced a plain-language "how it works" — the raw material for the essence.*

---

## 1. Distill the essence

> out of curiosity, can you please write an markdown of the watchdog alongside the blogpost where you
> describe the _functionality_ of the watchdog in minute detail, but don't restrict to any technical
> solution to the extent possible. include the lessons learned somewhere. you have the freedom to
> choose how this file is structured, how it should read, and what it looks like.
>
> the ultimate goal is to be able to share this file for others, they would input it's contents to
> their LLM that has access to their repo/environment, and could implement similar solution within
> their context. this requirement means we couldn't pin loki, mistral, gitea, for example.
>
> let's try it. spend as much time, thought, research, agents, whatever you need, in this. i'm not
> going to direct you or give you other input in how to write this. remember, the goal is to make a
> self-contained description of the watchdog, so that another LLM could reimplement it.

*Produced the first `ESSENCE.md`: a technology-agnostic, self-contained functional spec — roles
instead of products (no Loki/Mistral/Gitea), lessons learned included, written for another LLM to
reimplement.*

---

## 2. Name it, and place it in the landscape

> then a question, can you find anywhere in the internet a similar solution, where people share
> solutions by similar detailed means? and i don't mean simple prompts, i mean full systems or parts
> of systems defined like this or in another way.
>
> i would like to call this "the essence of a watchdog" so the file is an essence :)

*Researched prior art (spec-driven development — Spec Kit / Kiro / "specs are the new code"; pattern
catalogs — Hohpe's Enterprise Integration Patterns; build-your-own-x) and concluded the exact
combination sits in a gap. Coined the artifact type — "an essence" — and retitled the file.*

> please do

---

## 3. Refine the essence

> additional requirements:
>
> * try to strip design choices that are not universally accepted. for example, no using worktrees is
> not a generally accepted practice, but a consequence of basically my lack of environment setup.
> * add descriptions of unit tests, functional tests and integration tests, as you see fit.

*Stripped environment-specific choices (reframed to "a pristine, isolated copy — clone/worktree/
snapshot, your choice" instead of presenting "no worktrees" as a principle), and added a
unit / functional / integration testing section.*

---

## 4. Turn it into a runnable starter

> now, i would like to have a minimal setup, the context, the repo, to be able to add this file and
> tell you to build me a watchdog. the idea is to perhaps construct a github repo, or a folder within
> github, that people could check out and run the build, so they would have a "hello world" solution
> in place. something as simple as humanly/AI:ly possible, but still have all the necessary components.

> please setup a folder somewhere, i don't care that much where, to build this

*First runnable scaffold of the repo.*

---

## 5. Two languages, and the user's workflow

> i meant, have basically these fake/simple implementations of each role and have the agent build the
> pipeline, which kind of is the watchdog. i would preferably, i would like for two completely
> different implementations like one uses python and the other typescript.

> and what the user would do is checkout the repo, go to the context directory, prompt their LLM to
> say: "build me a service from this essence in this context". two distinct contexts to showcase the
> essence works.

*Reframed: ship the fake role-services as fixed "context"; the agent builds the watchdog itself. Two
stacks (Python + TypeScript) to prove the essence is portable.*

---

## 6. Make the context realistic — the closed loop

> the contexts should mimic a new user's context, that wouldn't have no knowledge about the pipeline,
> the watchdog or anything else related to this.

> but of course the building blocks should be there. and here they are the fake services that act on
> the roles.

> so i'm thinking, some code that runs and produces log lines to somewhere. the LLM builds the
> watchdog to read the log lines, and to patch the code, that is the code the produced the log lines.
> so the context-common roles services should be the log-producing service, log_store, triage_model,
> coding agent, sandbox, code host and notifier.

*The key pivot: each context is a realistic environment — a small buggy app that logs errors + simple
fakes for the seven roles. The watchdog (which the agent builds) patches the very code that produced
the logs.*

Two follow-up choices (answers to clarifying questions):
- the buggy app → **a tiny data-ingest CLI**
- the fake coding agent → **applies a real canned fix**, so the loop actually closes with no API key.

---

## 7. Outcome

> i tried it with a clean session, and it worked :) so please continue with typescript

*A fresh agent, given only the essence + the context, built the watchdog and the closed loop ran end
to end: bug → log → fix → PR → healed. Both the Python and TypeScript contexts were verified the same
way, then this repo was published.*
