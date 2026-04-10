let currentSport = 'football';
let cartCount = 0;
let cartItems = [];
let dataPollingInterval;

async function checkAuth() {
    const authRes = await fetch('/api/me');
    const auth = await authRes.json();
    const overlay = document.getElementById('auth-overlay');
    
    if (auth.logged_in) {
        overlay.style.display = 'none';
        if(auth.role === 'admin') {
            const adminBtn = `<button class="btn-sm" style="background:var(--accent-red); margin-top:5px; width:100%" onclick="window.location.href='/admin'">Admin Panel</button>`;
            document.querySelector('.user-profile').innerHTML += adminBtn;
        }
        initApp();
    } else {
        overlay.style.display = 'flex';
    }
}

function setAuthMode(mode) {
    const tabs = document.querySelectorAll('.auth-tab');
    tabs.forEach(t => t.classList.remove('active'));
    event.currentTarget.classList.add('active');
    document.getElementById('auth-submit').textContent = mode === 'login' ? 'Login' : 'Register';
    document.getElementById('auth-submit').dataset.mode = mode;
}

async function handleAuth(e) {
    e.preventDefault();
    const mode = document.getElementById('auth-submit').dataset.mode || 'login';
    const un = document.getElementById('auth-user').value;
    const pw = document.getElementById('auth-pass').value;

    const res = await fetch(`/api/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: un, password: pw })
    });
    const result = await res.json();
    if(result.success) {
        window.location.reload();
    } else {
        alert(result.message);
    }
}

async function logout() {
    await fetch('/api/logout', { method: 'POST' });
    window.location.reload();
}

async function fetchVenueData() {
    try {
        const res = await fetch('/api/venue_data');
        const json = await res.json();
        if(json.success && json.data) {
            updateUI(json.data);
        }
    } catch(err) {
        console.error("Polling error", err);
    }
}

function updateUI(data) {
    // Scoreboard
    const sportData = data[currentSport];
    if(sportData && document.querySelector('.match-status')) {
        document.querySelector('.match-status').innerHTML = `<span class="dot"></span> ${sportData.status}`;
        document.querySelector('.score-board').innerHTML = `
            <div class="team"><div class="team-logo home-team">${sportData.home.charAt(0)}</div><h2>${sportData.home}</h2></div>
            <div class="score"><h1>${sportData.score}</h1><p>${sportData.time}</p></div>
            <div class="team"><div class="team-logo away-team">${sportData.away.charAt(0)}</div><h2>${sportData.away}</h2></div>
        `;
    }

    // Wait Times
    if(data.wait_times) {
        if(document.getElementById('display-wt-restroom')) {
            document.getElementById('display-wt-restroom').textContent = data.wait_times.restroom;
            document.getElementById('display-wt-merch').textContent = data.wait_times.merch;
            document.getElementById('display-wt-pizza').textContent = data.wait_times.pizza;
        }
    }
}

function initApp() {
    // Sport Switcher Setup
    const sportButtons = document.querySelectorAll('.sport-switcher button');
    sportButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            sportButtons.forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            currentSport = e.currentTarget.getAttribute('data-sport');
            fetchVenueData(); // instant refresh
        });
    });

    // Cart Setup
    const addBtns = document.querySelectorAll('.add-btn');
    const badge = document.querySelector('.cart-nav .badge');
    const actionBtn = document.getElementById('checkout-btn');
    
    if(addBtns.length > 0) {
        addBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                cartCount++;
                cartItems.push(btn.getAttribute('data-item'));
                badge.textContent = cartCount;
                badge.style.display = 'block';
                
                const originalText = btn.textContent;
                btn.innerHTML = '<i class="fa-solid fa-check"></i>';
                btn.style.background = 'var(--accent-green)';
                setTimeout(() => { btn.textContent = '+'; btn.style.background = 'var(--accent-blue)'; }, 1000);
            });
        });

        actionBtn.addEventListener('click', async () => {
            if(cartItems.length === 0) { alert("Your cart is empty!"); return; }
            const originalText = actionBtn.textContent;
            actionBtn.textContent = "Processing...";
            actionBtn.disabled = true;

            try {
                const response = await fetch('/api/order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: cartItems })
                });
                const data = await response.json();
                if(data.success) {
                    alert(data.message);
                    cartItems = []; cartCount = 0; badge.style.display = 'none';
                } else { alert("Error: " + data.message); }
            } catch (error) {
                alert("Network error: Could not reach backend server.");
            } finally {
                actionBtn.textContent = originalText; actionBtn.disabled = false;
            }
        });
    }
    
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        // Highlight active route
        const route = window.location.pathname;
        if ((route === '/' && item.textContent.includes('Home')) ||
            (route === '/map' && item.textContent.includes('Map')) ||
            (route === '/order' && item.textContent.includes('Order')) ||
            (route === '/tickets' && item.textContent.includes('Tickets'))) {
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
        }
    });

    // Start data polling
    fetchVenueData();
    dataPollingInterval = setInterval(fetchVenueData, 3000);
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('auth-form')?.addEventListener('submit', handleAuth);
    checkAuth();
});
