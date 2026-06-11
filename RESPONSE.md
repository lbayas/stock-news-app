### Briefly describe your process for completing the project from start to finish. Include details on assumptions made and key decisions taken / tradeoffs made for each step (if relevant).

- I took the first 30 minutes to identify the main actors in the system and draw a diagram on paper. I new from the start that I needed to store pricing data and event data and have a correlation between the two per symbol as a primary architecture pattern. I also recognized that events can have higher or lower correlation with symbols depending on the context, so leveraging LLMs to help "score" higher or lower correlations from 0->1 made alot of sense to me. This allows us later, per symbol through the API, to show relevant results
- I next evaluated/debated what python tools I could use to accomplish the task (django vs fastapi), opted to go simpler with fast-api
- I next recognized that in a prodution scenario, we may need real time pricing, news feed, chakra integration, but that wasn't specified, so opted to go simpler and sync news from current point in time back to scope this project down given the time

### Are you happy with your solution? Why or why not?

For a proof of concept that is functional and implements the described use case yes. My key benchmark for success (or happiness rather) is if my solution satisfies test cases for the endpoints provided, which is does and for something done really quickly I am happy with the overall function.

### What would you do differently if you got to do this over again?

It would be nice to confirm some of these assumptions I made to make sure it aligns with what stakeholders want need so that I am designing the system to cater to stakeholder expectations. if they wanted a more production grade system, I would have opted for celery + redis, given this is primarily reads maybe pre-compute and cache symbols in redis so most reads hit cache and write from background workers continue to update database with latest data. There is no resiliency in the job system which is another reason to use celery + redis but that adds more tooling/infra.

### Did you get stuck anywhere? How’d you get unstuck?

I didn't get stuck anywhere per-say, it was a straight forward assignment IMHO and actually fun to do. I guess the only thing was just funding my OpenAI account with $10 to test everything. Actually one thing I did struggle with is the scale of the solution but opted to really try to scope this down as much as possible to top symbols. I also struggled with how async I wanted everything to be verse sync (slower) to have a good experience for API consumer.

Morevoer, time spent in the beginning made this a smooth process IMHO because I was able to build exactly what I envisioned after designing the system on paper (and in my head)
