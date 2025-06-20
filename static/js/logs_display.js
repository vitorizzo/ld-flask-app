// logs_display.js
function scrollLogToBottom() {
  const logDiv = document.querySelector('.log-viewer');
  if (logDiv) logDiv.scrollTop = logDiv.scrollHeight;
}

/*function cleanEmptyLogLines() {
  const rawLines = document.querySelectorAll('.text-muted');
  rawLines.forEach(line => {
    if (line.innerText.trim() === '') {
      line.remove();
    }
  });
}*/

function cleanEmptyLogLines() {
  document.querySelectorAll('.text-muted').forEach(line => {
    if (!line.textContent.trim()) line.remove();
  });
}
window.addEventListener('load', () => {
  scrollLogToBottom();
  cleanEmptyLogLines();
});
