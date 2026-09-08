-- YGO Reborn TCG-specific reviewed override for Project Ignis official/c88753985.lua
-- Fox Fire (88753985)
--
-- Upstream baseline reviewed: ProjectIgnis/CardScripts
--   14064037f42d0ae0bb9f8577d7eba2baad95e633
--
-- Current TCG English text requires Fox Fire to have been face-up at the start of
-- the Damage Step for its End Phase self-Summon to apply. Official Japanese OCG
-- Q&A explicitly says a face-down Defense Position Fox Fire that is attacked,
-- flipped, destroyed by that battle, and sent to the GY still activates in the
-- End Phase. The pinned Project Ignis script follows that OCG behavior because
-- EVENT_BATTLE_DESTROYED sees the post-flip previous face-up position.
--
-- Reborn uses current TCG text as authority. Record whether this exact Fox Fire
-- was face-down when it became an attack target. If that flag is still present
-- when the battle-destruction event occurs, do not register the End Phase summon.
-- A later attack while Fox Fire is already face-up replaces/clears the old flag.

--きつね火
--Fox Fire
local s,id=GetID()
function s.initial_effect(c)
	--Remember whether this card was face-down when selected as an attack target
	local e1=Effect.CreateEffect(c)
	e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_CONTINUOUS)
	e1:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)
	e1:SetCode(EVENT_BE_BATTLE_TARGET)
	e1:SetOperation(s.targetreg)
	c:RegisterEffect(e1)
	--Register the End Phase self-Summon only for the TCG-eligible battle case
	local e2=Effect.CreateEffect(c)
	e2:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_CONTINUOUS)
	e2:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)
	e2:SetCode(EVENT_BATTLE_DESTROYED)
	e2:SetOperation(s.regop)
	c:RegisterEffect(e2)
	--Cannot be Tributed for a Tribute Summon
	local e3=Effect.CreateEffect(c)
	e3:SetType(EFFECT_TYPE_SINGLE)
	e3:SetProperty(EFFECT_FLAG_SINGLE_RANGE)
	e3:SetRange(LOCATION_MZONE)
	e3:SetCode(EFFECT_UNRELEASABLE_SUM)
	e3:SetValue(1)
	c:RegisterEffect(e3)
end
function s.targetreg(e,tp,eg,ep,ev,re,r,rp)
	local c=e:GetHandler()
	c:ResetFlagEffect(id)
	if c:IsFacedown() then
		c:RegisterFlagEffect(id,RESET_PHASE|PHASE_BATTLE,0,1)
	end
end
function s.regop(e,tp,eg,ep,ev,re,r,rp)
	local c=e:GetHandler()
	if c:GetFlagEffect(id)>0 then return end
	if c:IsLocation(LOCATION_GRAVE) and c:IsReason(REASON_BATTLE) and c:IsPreviousPosition(POS_FACEUP) then
		local e1=Effect.CreateEffect(c)
		e1:SetDescription(aux.Stringid(id,0))
		e1:SetCategory(CATEGORY_SPECIAL_SUMMON)
		e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_TRIGGER_F)
		e1:SetCode(EVENT_PHASE+PHASE_END)
		e1:SetCountLimit(1)
		e1:SetRange(LOCATION_GRAVE)
		e1:SetTarget(s.sptg)
		e1:SetOperation(s.spop)
		e1:SetReset(RESETS_STANDARD_PHASE_END)
		c:RegisterEffect(e1)
	end
end
function s.sptg(e,tp,eg,ep,ev,re,r,rp,chk)
	if chk==0 then return true end
	Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,e:GetHandler(),1,0,0)
end
function s.spop(e,tp,eg,ep,ev,re,r,rp)
	if Duel.GetLocationCount(tp,LOCATION_MZONE)<=0 then return end
	if e:GetHandler():IsRelateToEffect(e) then
		Duel.SpecialSummon(e:GetHandler(),0,tp,tp,false,false,POS_FACEUP)
	end
end
