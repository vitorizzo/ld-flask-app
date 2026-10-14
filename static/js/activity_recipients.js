window.ActivityRecipients = row => {
 const assignments=[];
 if(row.users?.length)assignments.push('Utenti: '+row.users.map(user=>user.name).join(', '));
 if(row.roles?.length)assignments.push('Ruoli: '+row.roles.join(', '));
 if(row.target_min_weight!=null)assignments.push('Ruoli con peso ≥ '+row.target_min_weight);
 return assignments.join(' · ');
};
