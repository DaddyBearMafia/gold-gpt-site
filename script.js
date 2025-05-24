async function fetchGPTData() {
  try {
    const response = await fetch('gold_gpt_data.txt?_=' + new Date().getTime());
    const text = await response.text();
    document.getElementById('gptOutput').textContent = text;
  } catch (error) {
    document.getElementById('gptOutput').textContent = 'Error loading data.';
  }
}

// Refresh every 3 seconds
fetchGPTData();
setInterval(fetchGPTData, 3000);
