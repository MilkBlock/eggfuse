"""Train a conditional read address using synthetic pairs of token receipts."""
import torch


def fit_address(correlated=False, width=8, steps=80, seed=518, counterexamples=0, shared_route=False):
    # Labels name the partner's memory address. The latent field/role action
    # has no label: any projection yielding that address receives credit.
    rng = torch.Generator().manual_seed(518)
    with torch.random.fork_rng():
        torch.manual_seed(seed)
        policy = torch.nn.Sequential(torch.nn.Embedding(2, width), torch.nn.Tanh(),
                                     torch.nn.Linear(width, 8))
    roles = torch.arange(512) % 2
    fields = torch.randint(0, 1 << 16, (512, 4), generator=rng)
    if correlated:
        fields[:, 1] = fields[:, 0]
    if counterexamples:
        if not correlated or counterexamples % 2 or not 2 <= counterexamples <= len(fields):
            raise ValueError("counterexamples must cover both roles on the aliased fixture")
        fields[:counterexamples, 1] ^= 1
    addresses = fields[:, None, :].expand(-1, 2, -1)
    correct = ((torch.arange(2)[None, :, None] != roles[:, None, None]) &
               (addresses == fields[:, :1, None])).flatten(1)
    if shared_route:
        # This head takes only role as input. Every example with the same
        # role must use the same action, including deliberate renamings.
        correct = torch.stack([correct[roles == role].all(0) for role in range(2)])
        roles = torch.arange(2)
        if not correct.any(1).all():
            raise ValueError("training receipts cannot share one instruction per role")
    opt = torch.optim.Adam(policy.parameters(), lr=.03)
    for _ in range(steps):
        opt.zero_grad()
        logp = policy(roles).log_softmax(1)
        loss = -logp.masked_fill(~correct, -torch.inf).logsumexp(1).mean()
        loss.backward()
        opt.step()
    logits = policy(torch.arange(2)).detach()
    return dict(routes=[list(divmod(action, 4)) for action in logits.argmax(1).tolist()],
                logits=logits.tolist(), width=width, steps=steps, correlated=correlated,
                seed=seed, counterexamples=counterexamples, shared_route=shared_route)


def fit_renaming_study():
    """Hold training receipts fixed, vary initialization, data and objective."""
    settings = {
        "aliased": {},
        "wide_aliased": dict(width=32),
        "long_aliased": dict(steps=240),
        "two_renamed": dict(counterexamples=2),
        "shared_aliased": dict(shared_route=True),
        "shared_two_renamed": dict(shared_route=True, counterexamples=2),
    }
    checkpoints = {}
    arms = {}
    for name, options in settings.items():
        routes = []
        for seed in range(16):
            checkpoint = fit_address(correlated=True, seed=seed, **options)
            route = checkpoint["routes"]
            key = "-".join(str(4 * bank + field) for bank, field in route)
            checkpoints.setdefault(key, checkpoint)
            routes.append(key)
        arms[name] = routes
    return arms, checkpoints
