document.addEventListener("DOMContentLoaded", function() {
  var requestsTable = document.querySelector("#requestsTable");
  var requests = [];
  var filterStatus = "all";
  var searchTerm = "";

  function fetchRequests() {
    fetch("http://127.0.0.1:5001/requests_data")
      .then(function(res) {
        if (!res.ok) {
          throw new Error("HTTP error! status: " + res.status);
        }
        return res.json();
      })
      .then(function(data) {
        console.log("Data received:", data);
        
        if (!data || !data.requests || !Array.isArray(data.requests)) {
          throw new Error("Invalid data format received");
        }
        
        requests = data.requests;
        renderRequests();
      })
      .catch(function(error) {
        console.error("Error fetching requests:", error);
        if (requestsTable) {
          requestsTable.innerHTML = '<tr><td colspan="8" class="text-center text-danger">Помилка завантаження даних: ' + error.message + '</td></tr>';
        }
      });
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    var d = new Date(dateStr);
    var day = d.getDate();
    var month = d.getMonth() + 1;
    var year = d.getFullYear();
    var hours = d.getHours();
    var minutes = d.getMinutes();

    // Add leading zeros
    day = day < 10 ? '0' + day : day;
    month = month < 10 ? '0' + month : month;
    hours = hours < 10 ? '0' + hours : hours;
    minutes = minutes < 10 ? '0' + minutes : minutes;

    return day + '.' + month + '.' + year + ' ' + hours + ':' + minutes;
  }

  function renderRequests() {
    console.log("Rendering requests, table element:", requestsTable);
    console.log("Requests data:", requests);
    
    if (!requestsTable) {
      console.error("Table element not found!");
      return;
    }
    
    requestsTable.innerHTML = "";

    if (!requests || requests.length === 0) {
      console.log("No requests to display");
      requestsTable.innerHTML = '<tr><td colspan="8" class="text-center text-muted">Заявок поки немає</td></tr>';
      return;
    }

    console.log("Starting to render", requests.length, "requests");

    for (var i = 0; i < requests.length; i++) {
      var r = requests[i];
      var row = document.createElement("tr");
      
      // Set row class based on status
      if (r.status === "done") {
        row.className = "table-success";
      } else if (r.status === "error") {
        row.className = "table-danger";
      } else {
        row.className = "table-warning";
      }

      row.setAttribute("data-index", i);
      
      // Create status badge
      var statusBadge = '';
      if (r.status === "done") {
        statusBadge = '<span class="badge bg-success">Виконано</span>';
      } else if (r.status === "error") {
        statusBadge = '<span class="badge bg-danger">Не працює</span>';
      } else {
        statusBadge = '<span class="badge bg-warning text-dark">Очікує</span>';
      }

      // Create action buttons
      var completeBtn = '';
      var notWorkingBtn = '';
      
      if (r.status !== "done") {
        completeBtn = '<button class="btn btn-sm btn-success complete-btn" data-action="done" data-index="' + i + '">✅</button>';
      }
      
      if (!r.status || (r.status !== "error" && r.status !== "done")) {
        notWorkingBtn = '<button class="btn btn-sm btn-warning complete-btn" data-action="not_working" data-index="' + i + '">🚫</button>';
      }

      // Build the row HTML
      var rowHTML = '';
      rowHTML += '<td>' + formatDate(r.timestamp) + '</td>';
      rowHTML += '<td>' + r.address + (r.entrance ? ' п.' + r.entrance : '') + '</td>';
      rowHTML += '<td>' + (r.name || '') + '</td>';
      rowHTML += '<td>' + r.issue + '</td>';
      rowHTML += '<td>' + (r.phone || '') + '</td>';
      rowHTML += '<td>' + (r.completed_time ? formatDate(r.completed_time) : '') + '</td>';
      rowHTML += '<td>' + statusBadge + '</td>';
      rowHTML += '<td>';
      rowHTML += '<div class="btn-group">';
      rowHTML += completeBtn;
      rowHTML += notWorkingBtn;
      rowHTML += '<button class="btn btn-sm btn-danger delete-btn" data-index="' + i + '">🗑️</button>';
      rowHTML += '</div>';
      rowHTML += '</td>';
      
      row.innerHTML = rowHTML;
      requestsTable.appendChild(row);
    }
  }

  // Event handler for table buttons
  if (requestsTable) {
    requestsTable.addEventListener("click", function(e) {
      var btn = e.target.closest("button");
      var row = e.target.closest("tr");
      if (!row || !row.getAttribute("data-index")) return;

      var index = parseInt(row.getAttribute("data-index"));
      var req = requests[index];

      // Complete/Not working buttons
      if (btn && btn.classList.contains("complete-btn")) {
        var action = btn.getAttribute("data-action");
        fetch("http://127.0.0.1:5001/update_status/" + index + "/" + action, { method: "POST" })
          .then(function(res) { return res.json(); })
          .then(function(data) {
            if (data.success) {
              if (action === "done") {
                requests[index].status = "done";
                requests[index].completed = true;
                requests[index].completed_time = new Date().toISOString();
              } else if (action === "not_working") {
                requests[index].status = "error";
              }
              renderRequests();
            }
          })
          .catch(function(error) {
            console.error("Error updating status:", error);
          });
      }

      // Delete button
      if (btn && btn.classList.contains("delete-btn")) {
        if (confirm("Видалити цю заявку?")) {
          fetch("http://127.0.0.1:5001/delete_request/" + index, { method: "POST" })
            .then(function(res) { return res.json(); })
            .then(function(data) {
              if (data.success) {
                requests.splice(index, 1);
                renderRequests();
              }
            })
            .catch(function(error) {
              console.error("Error deleting request:", error);
            });
        }
      }
    });
  }

  // Initial load
  fetchRequests();
  
  // Refresh every 30 seconds
  setInterval(fetchRequests, 30000);
});