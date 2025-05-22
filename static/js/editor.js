// editor.js
document.addEventListener('DOMContentLoaded', () => {
  console.log('Editor JS loaded');

  // 1) Riferimenti DOM
  const sel        = document.getElementById('connection_id');
  const btnNew     = document.getElementById('btn-new');
  const btnEdit    = document.getElementById('btn-edit-meta');
  const manageLink = document.getElementById('manage-actions');
  const saveBtn    = document.getElementById('saveBtn');
  const editor     = document.getElementById('editor');
  const metaCon    = document.getElementById('meta-form-container');
  const metaForm   = document.getElementById('meta-form');
  const inputs     = {
    board_id:     document.getElementById('in-board_id'),
    board_name:   document.getElementById('in-board_name'),
    api_key:      document.getElementById('in-api_key'),
    token:        document.getElementById('in-token'),
    callback_url: document.getElementById('in-callback_url'),
  };
  let currentId  = null;
  let instance   = null;

  // Funzioni e handler (sposta qui tutto il codice JS di editor)
  // — addNode, initJsPlumb, fetch connessioni, sel change handler,
  //   submit metaForm, btnNew, btnEdit, saveBtn, initJsPlumb primo init …

  // … copia al 100% il tuo script inline qui dentro …

});
