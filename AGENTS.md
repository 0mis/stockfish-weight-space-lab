# Required helper-agent settings

Use model `gpt-6-astra` with reasoning effort `max` for every spawned helper
agent, including nested helpers. Explicitly set both fields on every spawn.
Use `fork_turns: "none"` when the collaboration API requires it for overrides.

Use at most 6 helper agents concurrently across the entire agent tree.
Spawn helpers only when the user's request or applicable instructions authorize
delegation. Give each helper the context needed for its bounded task.

If these exact model and reasoning settings are unavailable, report the
limitation instead of substituting another model or reasoning effort.

This requirement reflects the user's latest explicit model choice and supersedes
the earlier GPT-6.1 Sol and Astra xhigh settings. Retire helpers using any other
model or reasoning effort, and create a helper with these exact settings when
further delegated work is needed.
