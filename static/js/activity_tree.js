/* Shared collapse state survives list refreshes on Home and Activities. */
window.ActivityTree = (() => {
 const closed=new Set();
 function title(row,label,hasChildren){return hasChildren?'<button type="button" class="activity-tree-title" data-tree-toggle="'+row.id+'" aria-expanded="'+!closed.has(row.id)+'">'+(closed.has(row.id)?'▸ ':'▾ ')+label+'</button>':'<strong>'+label+'</strong>';}
 function hidden(id){return closed.has(id)?' hidden':'';}
 document.addEventListener('click',event=>{const button=event.target.closest('[data-tree-toggle]');if(!button)return;const id=Number(button.dataset.treeToggle),list=button.closest('.activity-tree-node').querySelector(':scope > ul.activity-tree');if(!list)return;
  if(closed.has(id))closed.delete(id);else closed.add(id);list.hidden=closed.has(id);button.setAttribute('aria-expanded',String(!list.hidden));button.firstChild.textContent=(list.hidden?'▸ ':'▾ ')+button.firstChild.textContent.slice(2);
 });
 return {title,hidden};
})();
