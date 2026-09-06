"""Empirical maximin gate. Never accept proxy scores or missing games as payoffs."""
import math


def wilson_lower(wins,total,z=1.96):
    if total<=0 or not 0<=wins<=total:raise ValueError('Invalid completed-game count')
    p=wins/total
    return (p+z*z/(2*total)-z*math.sqrt(p*(1-p)/total+z*z/(4*total*total)))/(1+z*z/total)


def maximin(payoffs):
    """Rows contain certified first/second-seat samples for every adversary.

    Conservative wins-only lower bound; draws count as non-wins. Multiplicity
    correction and adaptive-selection holdout are still required for promotion.
    """
    if not payoffs:raise ValueError('Empty population')
    opponents=set(next(iter(payoffs.values())))
    if not opponents:raise ValueError('No adversaries')
    scores={}
    for deck,row in payoffs.items():
        if set(row)!=opponents:raise ValueError('Incomplete adversary matrix')
        bounds=[]
        for seats in row.values():
            if set(seats)!={'first','second'}:raise ValueError('Both seats required')
            for sample in seats.values():
                if sample.get('certified') is not True or sample.get('unsupported',0) or sample.get('timeouts',0):
                    raise ValueError('Uncertified/incomplete simulation')
                bounds.append(wilson_lower(sample['wins'],sample['games']))
        scores[deck]=min(bounds)
    return max(scores,key=scores.get),scores


def double_oracle(population,evaluate,best_response,max_rounds=10):
    """Callback orchestration; no shipped fake opponent or fake duel evaluator.

    best_response receives the full matrix and incumbent, and returns an unseen
    candidate or None. None means search exhausted its budget, NOT equilibrium.
    """
    population=list(population);history=[]
    for iteration in range(max_rounds):
        matrix=evaluate(population)
        incumbent,bounds=maximin(matrix)
        challenger=best_response(population,matrix,incumbent)
        history.append(dict(iteration=iteration,incumbent=incumbent,bounds=bounds,challenger=challenger))
        if challenger is None or challenger in population:break
        population.append(challenger)
    return population,history
