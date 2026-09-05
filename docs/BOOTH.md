# The EnGenius booth demo

AT3 is a booth, 22 Oct, 30 percent, with a poster criterion the Part A
presentation did not have. The audience is two audiences at once: markers who
will probe whether the thing is real, and the public, who will give you ninety
seconds.

## The design decision, and why it is not Streamlit

The supervisor suggested Streamlit and it was the right suggestion in general.
For a booth specifically it is the wrong tool, for four reasons that only show up
on the day.

1. **It needs a server running.** A booth laptop sleeps, loses power, or gets
   closed. A dead Streamlit process is a dead stand.
2. **Every widget change is a network round trip.** The core interaction here is
   dragging a position and watching a verdict change. Round trip latency turns
   that from a discovery into a wait.
3. **It cannot be handed to anyone.** A marker who wants to look again after the
   event, or a visitor who wants to show a colleague, cannot take a running
   process with them.
4. **It needs an install that does not exist on this machine**, and a booth is a
   bad place to find out that a virtual environment broke.

**What is built instead: a self-contained page.** Zero dependencies, opens in any
browser, works with no network, and can be sent to anyone as a link. It runs on
the phone in a visitor's hand while they are standing at the stand.

**The credibility problem this creates, and how it is solved.** A page with no
Python behind it invites the question "did you just draw this?". The answer is
that **every number the page shows was computed by the analysis code in this
repository**, on the real corpus, and baked into the page as a response surface.
The visitor is not interacting with a simulation of the result. They are
interacting with a lookup over the actual measurement, sampled on a grid. The
generator is `analysis/make_booth_surface.py` and it imports `pooled_consensus`
directly, so the statistic on screen is the statistic in the paper.

That is also *faster* than computing live, which is what makes the interaction
feel instant rather than laggy.

## The one idea the booth has to land

> You can lie about where you are. The radio can catch you. But only if you lie
> big enough, and only if enough receivers are listening.

Everything else is detail. A visitor who leaves with that sentence has the paper.

## The interaction: the visitor is the attacker

Not a slideshow with a play button. The visitor takes the adversary's seat and
tries to get away with it, which is the only framing that makes a stranger care
about a consistency ratio.

**On screen:** a stretch of road from above. Their car, its true position marked.
Receivers along the road. A claimed position they control. A verdict.

**Four moves, in this order, each one a discovery rather than an explanation.**

| move | what they do | what they find |
|---|---|---|
| 1 | lie, with **one receiver** listening | never caught, at any distance. One receiver cannot tell, and it is not bad at it, it *cannot* |
| 2 | turn on **the other receivers** | now there is a boundary. Slide down until you get away with it and you have personally found the detection floor |
| 3 | lie **sideways** instead of along the road | you get away with far more. The geometry has a weak direction and you just found it |
| 4 | turn on **the map constraint** | the sideways trick stops working |

Move 1 is the hook, because the answer is counterintuitive and immediate. Move 2
is the result. Move 3 is the part that makes a marker sit up, because the visitor
rediscovers by hand the direction a 72 direction search found and the Cramer Rao
bound predicts. Move 4 is the engineering.

## What is on the poster

The poster carries the same arc so the story survives a flat battery, which is
the actual risk at a booth. Four panels matching the four moves, the floor figure
as the centre, and the one sentence above as the title rather than the project
title.

## The ninety second script

For when someone stops and you have one chance.

> "This car is lying about where it is. Its messages are perfectly signed, so
> cryptography says they are fine. Have a go: drag it anywhere you like."
>
> *(they drag, nothing happens)*
>
> "Right. One receiver cannot catch you no matter how far you go. Now watch."
>
> *(turn on the other receivers)*
>
> "Now find the smallest lie you can get away with."
>
> *(they find about fifty metres)*
>
> "That number is the result. It is not a limit of our detector, it is a limit of
> the physics. Now try lying sideways across the road instead."

## What it must never do

- **Never say "detected 99 percent".** The honest numbers are more interesting
  than inflated ones, and the whole contribution is a limit rather than a score.
- **Never hide the floor.** The thing that makes this work publishable is that
  small lies are not detectable, and a demo that obscures that is selling
  something else.
- **Never require the network.** Conference wifi does not work. Ever.
