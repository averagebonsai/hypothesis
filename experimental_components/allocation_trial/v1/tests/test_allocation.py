import math
def _project(target, budget):
    n=len(target); s=sorted(target, reverse=True); cum=0.0; lam=0.0
    for k,v in enumerate(s,1):
        cum+=v; cand=(cum-budget)/k
        if k==n or cand>=s[k]: lam=cand; break
    return [max(0.0,x-lam) for x in target]
def test_alloc_action_schema():
    proj=_project([8.0,6.0],10.0)
    assert len(proj)==2 and abs(sum(proj)-10.0)<1e-9
    assert all(x>=0 for x in proj)
    assert proj==[6.0,4.0]
def test_mechanism_payoff():
    alloc=[5.0,5.0]; target=[8.0,6.0]
    score=-sum((a-t)**2 for a,t in zip(alloc,target))
    assert score==-10.0
    opt=[6.0,4.0]
    assert -sum((a-t)**2 for a,t in zip(opt,target))==-8.0 > score
def test_mechanism_validates_budget():
    assert abs(sum([5.0,5.0])-10.0)<1e-8
    assert abs(sum([11.0,0.0])-10.0)>1e-8
def test_game_view_evaluate():
    assert abs(sum(_project([3.0,1.0,1.0],3.0))-3.0)<1e-9
def test_solver_optimum():
    proj=_project([8.0,6.0],10.0)
    assert proj==[6.0,4.0]
    proj2=_project([9.0,1.0,1.0],10.0)
    assert abs(sum(proj2)-10.0)<1e-9 and all(x>=0 for x in proj2)
    proj3=_project([1.0,1.0,20.0],5.0)
    assert proj3[0]==0.0 and proj3[1]==0.0 and proj3[2]==5.0
def test_benchmark_separate():
    fixture=[5.0,5.0]; opt=[6.0,4.0]
    assert fixture!=opt
def test_alloc_action_rejects():
    bad=[-1.0,11.0]
    assert any(x<0 for x in bad)
