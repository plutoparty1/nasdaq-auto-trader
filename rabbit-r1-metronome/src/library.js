export class Library {
  confirming = null;
  saving = false;
  constructor(state, save, load, notify) {
    this.state = state;
    this.save = save;
    this.load = load;
    this.notify = notify;
    this.list = document.querySelector('#song-list');
    this.form = document.querySelector('#save-form');
    this.title = document.querySelector('#song-title');
    this.button = document.querySelector('#save-song');
    this.form.addEventListener('submit', event => { event.preventDefault(); void this.add(); });
  }
  async add() {
    if (this.saving || this.button.disabled) return;
    const title = this.title.value.trim();
    if (!title) { this.notify('Enter a song title.'); this.title.focus(); return; }
    if (this.state.songs.length >= 100) { this.notify('Maximum 100 songs. Delete one to save another.'); return; }
    const song = { ...this.state.settings, accents: [...this.state.settings.accents], title,
      id: globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}` };
    this.saving = true;
    this.button.disabled = true;
    this.state.songs.push(song);
    this.render();
    try {
      await this.save();
      this.title.value = '';
      this.notify(`Saved · ${song.bpm}-${title}`);
    } catch {
      this.state.songs = this.state.songs.filter(item => item.id !== song.id);
      this.notify('Could not save song. Try again.');
    } finally {
      this.saving = false;
      this.button.disabled = false;
      this.render();
    }
  }
  async remove(id) {
    if (this.saving) return;
    if (this.confirming !== id) { this.confirming = id; this.render(); return; }
    const previous = this.state.songs;
    this.saving = true;
    this.state.songs = previous.filter(song => song.id !== id);
    this.confirming = null;
    this.render();
    try { await this.save(); this.notify('Song deleted.'); }
    catch { this.state.songs = previous; this.notify('Could not delete song. Try again.'); }
    finally { this.saving = false; this.render(); }
  }
  render() {
    document.querySelector('#song-count').textContent = `${this.state.songs.length} ${this.state.songs.length === 1 ? 'song' : 'songs'}`;
    document.querySelector('#library-empty').hidden = this.state.songs.length > 0;
    this.list.replaceChildren();
    for (const song of this.state.songs) {
      const row = document.createElement('div');
      row.className = 'song-row';
      const button = document.createElement('button');
      button.className = 'song-load';
      button.disabled = this.saving;
      button.setAttribute('aria-label', `Load ${song.bpm}-${song.title}`);
      const title = document.createElement('strong');
      title.textContent = `${song.bpm}-${song.title}`;
      const details = document.createElement('span');
      details.textContent = `4/4 · ${['♩', '♪', '3'][song.subdivision - 1]} · ${song.mute ? 'Silent' : song.sound === 'drum' ? 'Drum' : 'Melody'}`;
      button.append(title, details);
      button.addEventListener('click', () => this.load(song));
      const remove = document.createElement('button');
      const confirm = this.confirming === song.id;
      remove.className = `song-delete${confirm ? ' confirm' : ''}`;
      remove.textContent = confirm ? 'Confirm' : 'Delete';
      remove.disabled = this.saving;
      remove.setAttribute('aria-label', `${song.title} ${confirm ? 'confirm delete' : 'delete'}`);
      remove.addEventListener('click', () => void this.remove(song.id));
      row.append(button, remove);
      this.list.append(row);
    }
  }
}
