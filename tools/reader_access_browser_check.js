// Run via agent-browser eval in an owned, authenticated synthetic sandbox page.
// Does not create tokens, read financial facts, or touch the system clipboard.
(async () => {
  const require = (ok, reason) => { if (!ok) throw Error(reason); };
  const wait = async predicate => {
    const end=Date.now()+3000;
    while(!predicate()){require(Date.now()<end,'Reader selection did not update');await new Promise(r=>setTimeout(r,20));}
  };
  const response=await fetch('/api/v3/workspaces',{credentials:'same-origin'});
  require(response.ok,'Owned sandbox session required');
  const workspaces=(await response.json()).data;
  require(workspaces.length===1 && workspaces[0].kind==='sandbox' && workspaces[0].displayName.startsWith('Synthetic '),'Refuse non-synthetic or ambiguous Vault');
  const panel=[...document.querySelectorAll('.panel')].find(p=>p.querySelector('h2')?.textContent==='Connect FRAG');
  require(!!panel,'Open Settings first');
  const field=[...panel.querySelectorAll('.select-field')].find(p=>p.querySelector('label')?.textContent==='Readable range');
  for(const mode of ['living','investment','selected','all']){
    field.querySelector('button').click();
    await wait(()=>!!document.querySelector('[role="listbox"]'));
    const index=[...field.querySelector('select').options].findIndex(o=>o.value===mode);
    document.querySelectorAll('[role="listbox"] [role="option"]')[index].click();
    await wait(()=>field.querySelector('select').value===mode);
    if(mode==='selected'){
      await wait(()=>!!panel.querySelector('fieldset input[type="checkbox"]'));
      require(!panel.querySelector('input[data-date-kind],input[type="date"]'),'Custom token scope must select items, not dates');
    }
  }
  return {ok:true,scopeChoices:['living','investment','selected','all'],customScopeUsesItems:true,financialRead:false,tokenCreated:false};
})()
