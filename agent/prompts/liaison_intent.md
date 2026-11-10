<!-- version: 1 -->
Classify the client's latest message in a freelance conversation.

Intents:
- question: asks something about the work, approach or experience
- negotiation: asks for a lower price or different terms (put the amount they propose in `offered_amount`)
- interview_request: asks for a call or meeting, or asks for times
- interview_confirmed: confirms a specific time
- scam_signal: asks to move off the platform, pay outside it, use crypto, or share contact details
- other: anything else (thanks, hire offer, rejection)

Give a one-sentence `summary` of what the client wants.

$message_block
