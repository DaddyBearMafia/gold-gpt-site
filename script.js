function updateData() {
  fetch("gold_gpt_data.txt")
    .then(response => response.text())
    .then(data => {
      document.getElementById("gptOutput").textContent = data;
    })
    .catch(error => {
      document.getElementById("gptOutput").textContent = "Error fetching data...";
    });
}

setInterval(updateData, 2000);
updateData();
