-- YGO Reborn reviewed override for Red-Eyes Darkness Metal Dragon (88264978)
--
-- Required Reborn policy: use the latest official card text/errata.
-- Verified against the official Yu-Gi-Oh! TCG Card Database on 2026-09-07.
--
-- Pinned Project Ignis CardScripts baseline:
--   49b0af044cebcb92f3f23211ef436971e1fc16fb
-- At that revision, official/c88264978.lua is absent, while the current-errata
-- implementation for the real card code is stored at pre-errata/c88264978.lua.
-- The ordinary solver script loader therefore cannot initialize card 88264978
-- and raises CallCardFunction(c88264978.initial_effect).  This reviewed override
-- exposes the pinned current-errata behavior at the real card code; it does not
-- use the pre-errata substitute script official/c88264988.lua.
--
-- Current intended behavior:
-- 1) From hand, Special Summon this card by banishing 1 face-up Dragon you
--    control; this procedure is once per turn.
-- 2) During your Main Phase, Special Summon 1 Dragon from your hand or GY,
--    except another Red-Eyes Darkness Metal Dragon; this effect is independently
--    once per turn.

local s,id=GetID()
function s.initial_effect(c)
	--Special Summon procedure from the hand
	local e1=Effect.CreateEffect(c)
	e1:SetType(EFFECT_TYPE_FIELD)
	e1:SetCode(EFFECT_SPSUMMON_PROC)
	e1:SetProperty(EFFECT_FLAG_UNCOPYABLE)
	e1:SetRange(LOCATION_HAND)
	e1:SetCountLimit(1,id,EFFECT_COUNT_CODE_OATH)
	e1:SetCondition(s.spcon1)
	e1:SetTarget(s.sptg1)
	e1:SetOperation(s.spop1)
	c:RegisterEffect(e1)
	--Special Summon 1 other Dragon from hand or GY
	local e2=Effect.CreateEffect(c)
	e2:SetDescription(aux.Stringid(id,0))
	e2:SetCategory(CATEGORY_SPECIAL_SUMMON)
	e2:SetType(EFFECT_TYPE_IGNITION)
	e2:SetRange(LOCATION_MZONE)
	e2:SetCountLimit(1,{id,1})
	e2:SetTarget(s.sptg)
	e2:SetOperation(s.spop)
	c:RegisterEffect(e2)
end
s.listed_names={id}

function s.spfilter(c,ft)
	return c:IsFaceup() and c:IsRace(RACE_DRAGON) and c:IsAbleToRemoveAsCost()
		and (ft>0 or c:GetSequence()<5)
end
function s.spcon1(e,c)
	if c==nil then return true end
	local tp=c:GetControler()
	local ft=Duel.GetLocationCount(tp,LOCATION_MZONE)
	local rg=Duel.GetMatchingGroup(s.spfilter,tp,LOCATION_MZONE,0,nil,ft)
	return ft>-1 and #rg>0 and aux.SelectUnselectGroup(rg,e,tp,1,1,nil,0)
end
function s.sptg1(e,tp,eg,ep,ev,re,r,rp,c)
	local ft=Duel.GetLocationCount(tp,LOCATION_MZONE)
	local rg=Duel.GetMatchingGroup(s.spfilter,tp,LOCATION_MZONE,0,nil,ft)
	local g=aux.SelectUnselectGroup(rg,e,tp,1,1,nil,1,tp,HINTMSG_REMOVE,nil,nil,true)
	if #g==0 then return false end
	g:KeepAlive()
	e:SetLabelObject(g)
	return true
end
function s.spop1(e,tp,eg,ep,ev,re,r,rp,c)
	local g=e:GetLabelObject()
	if not g then return end
	Duel.Remove(g,POS_FACEUP,REASON_COST)
	g:DeleteGroup()
end

function s.filter(c,e,tp)
	return c:IsRace(RACE_DRAGON) and not c:IsCode(id)
		and c:IsCanBeSpecialSummoned(e,0,tp,false,false)
end
function s.sptg(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
	if chk==0 then
		return Duel.GetLocationCount(tp,LOCATION_MZONE)>0
			and Duel.IsExistingMatchingCard(s.filter,tp,LOCATION_GRAVE|LOCATION_HAND,0,1,nil,e,tp)
	end
	Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,1,tp,LOCATION_GRAVE|LOCATION_HAND)
end
function s.spop(e,tp,eg,ep,ev,re,r,rp)
	if Duel.GetLocationCount(tp,LOCATION_MZONE)<=0 then return end
	Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SPSUMMON)
	local g=Duel.SelectMatchingCard(tp,aux.NecroValleyFilter(s.filter),tp,
		LOCATION_GRAVE|LOCATION_HAND,0,1,1,nil,e,tp)
	if #g>0 then
		Duel.SpecialSummon(g,0,tp,tp,false,false,POS_FACEUP)
	end
end
