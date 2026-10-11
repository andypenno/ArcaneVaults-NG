Scriptname ArcaneSpells extends activemagiceffect

Int Property SpellType Auto

; General Functions
Event OnEffectStart(Actor akTarget, Actor akCaster)	
	if SpellType == 0
		ArcaneVaults.ContainerRedirect()
	elseif SpellType == 1
		ArcaneVaults.OffloadItems()
	endif
EndEvent