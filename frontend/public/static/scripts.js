const form = document.getElementById('search-form');
const input = document.getElementById('search-input');
const list = document.getElementById('results-list');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    list.innerHTML = '<li>Loading...</li>';
    try {
        const res = await fetch(`/api/movie${q ? '?q=' + encodeURIComponent(q) : ''}`);
        const movies = await res.json();
        if (!movies.length) {
            list.innerHTML = '<li>No results found.</li>';
            return;
        }
        list.innerHTML = movies.map(m =>
            `<li><a href="/movie/${m.imdb_id}/">${m.title}</a> ${m.release_year ? '(' + m.release_year + ')' : ''} ${m.rating ? '⭐ ' + m.rating : ''}</li>`
        ).join('');
    } catch (err) {
        list.innerHTML = '<li>Error loading results.</li>';
    }
});
