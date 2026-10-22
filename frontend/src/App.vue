<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, tokenStore } from '@/lib/api'
import { itemsApi } from '@/features/items/api'
import { aiApi } from '@/features/ai/api'
import { uploadsApi } from '@/features/uploads/api'
import type {
  AppMeta,
  ChatMessage,
  Item,
  ItemCreate,
  ItemStatus,
  ItemUpdate,
  TokenResponse,
  UploadFileItem,
  User,
} from '@/types'

type Tab = 'example' | 'ai' | 'uploads'
const meta = ref<AppMeta | null>(null)
const healthy = ref<boolean | null>(null)
const currentTab = ref<Tab>('example')
const user = ref<User | null>(null)
const authOpen = ref(false)
const authMode = ref<'login' | 'register'>('login')
const authForm = ref({ email: '', password: '', name: '' })
const authError = ref('')
const authBusy = ref(false)

const items = ref<Item[]>([])
const total = ref(0)
const search = ref('')
const statusFilter = ref('all')
const itemBusy = ref(false)
const itemError = ref('')
const itemModalOpen = ref(false)
const editing = ref<Item | null>(null)
const itemForm = ref<{ title: string; description: string; status: ItemStatus }>({
  title: '', description: '', status: 'todo',
})
let searchTimer: ReturnType<typeof setTimeout> | undefined

const messages = ref<ChatMessage[]>([])
const prompt = ref('')
const aiBusy = ref(false)
const aiError = ref('')
const files = ref<UploadFileItem[]>([])
const uploadBusy = ref(false)
const uploadError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)

const navItems = computed(() => [
  { key: 'example' as const, label: 'Пример CRUD', icon: '▤' },
  ...(meta.value?.features.ai ? [{ key: 'ai' as const, label: 'AI-пример', icon: '✦' }] : []),
  ...(meta.value?.features.uploads ? [{ key: 'uploads' as const, label: 'Загрузка файлов', icon: '⇧' }] : []),
])
const inProgress = computed(() => items.value.filter((item) => item.status === 'in_progress').length)
const done = computed(() => items.value.filter((item) => item.status === 'done').length)
const statusLabels: Record<ItemStatus, string> = {
  todo: 'В планах', in_progress: 'В работе', done: 'Готово',
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'Произошла ошибка'
}

async function loadItems() {
  itemBusy.value = true
  itemError.value = ''
  try {
    const page = await itemsApi.list({
      q: search.value.trim() || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value as ItemStatus,
    })
    items.value = page.items
    total.value = page.total
  } catch (error) {
    itemError.value = errorText(error)
  } finally {
    itemBusy.value = false
  }
}

async function loadMeta() {
  try {
    const [appMeta, health] = await Promise.all([
      api.get<AppMeta>('/meta'),
      api.get<{ status: string }>('/health').catch(() => null),
    ])
    meta.value = appMeta
    healthy.value = health?.status === 'ok'
    if (appMeta.features.auth && tokenStore.get()) {
      try {
        user.value = await api.get<User>('/auth/me')
      } catch {
        tokenStore.set(null)
      }
    }
  } catch {
    healthy.value = false
  }
}

function openItem(item?: Item) {
  editing.value = item ?? null
  itemForm.value = item
    ? { title: item.title, description: item.description, status: item.status }
    : { title: '', description: '', status: 'todo' }
  itemError.value = ''
  itemModalOpen.value = true
}

async function saveItem() {
  const payload: ItemCreate = {
    title: itemForm.value.title.trim(),
    description: itemForm.value.description.trim(),
    status: itemForm.value.status,
  }
  if (!payload.title) {
    itemError.value = 'Название обязательно'
    return
  }
  itemBusy.value = true
  itemError.value = ''
  try {
    if (editing.value) await itemsApi.update(editing.value.id, payload satisfies ItemUpdate)
    else await itemsApi.create(payload)
    itemModalOpen.value = false
    await loadItems()
  } catch (error) {
    itemError.value = errorText(error)
  } finally {
    itemBusy.value = false
  }
}

async function cycleStatus(item: Item) {
  const next: Record<ItemStatus, ItemStatus> = { todo: 'in_progress', in_progress: 'done', done: 'todo' }
  await itemsApi.update(item.id, { status: next[item.status] })
  await loadItems()
}

async function deleteItem(item: Item) {
  if (!window.confirm(`Удалить «${item.title}»?`)) return
  try {
    await itemsApi.delete(item.id)
    await loadItems()
  } catch (error) {
    itemError.value = errorText(error)
  }
}

async function submitAuth() {
  authBusy.value = true
  authError.value = ''
  try {
    const path = authMode.value === 'login' ? '/auth/login' : '/auth/register'
    const data = await api.post<TokenResponse>(path, authMode.value === 'login'
      ? { email: authForm.value.email, password: authForm.value.password }
      : authForm.value)
    tokenStore.set(data.access_token)
    user.value = data.user
    authOpen.value = false
  } catch (error) {
    authError.value = errorText(error)
  } finally {
    authBusy.value = false
  }
}

function logout() {
  tokenStore.set(null)
  user.value = null
}

async function sendPrompt() {
  const content = prompt.value.trim()
  if (!content || aiBusy.value) return
  messages.value.push({ role: 'user', content })
  prompt.value = ''
  aiBusy.value = true
  aiError.value = ''
  try {
    const result = await aiApi.chat(messages.value)
    messages.value.push({ role: 'assistant', content: result.reply })
  } catch (error) {
    aiError.value = errorText(error)
  } finally {
    aiBusy.value = false
  }
}

async function loadFiles() {
  uploadError.value = ''
  try {
    files.value = await uploadsApi.list()
  } catch (error) {
    uploadError.value = errorText(error)
  }
}

async function uploadFile(file?: File) {
  if (!file) return
  uploadBusy.value = true
  uploadError.value = ''
  try {
    await uploadsApi.upload(file)
    await loadFiles()
  } catch (error) {
    uploadError.value = errorText(error)
  } finally {
    uploadBusy.value = false
  }
}

watch([search, statusFilter], () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadItems, 300)
})
watch(currentTab, (tab) => {
  if (tab === 'uploads' && files.value.length === 0) void loadFiles()
})
onMounted(() => {
  void loadMeta()
  void loadItems()
  window.addEventListener('auth:logout', logout)
})
onUnmounted(() => {
  clearTimeout(searchTimer)
  window.removeEventListener('auth:logout', logout)
})
</script>

<template>
  <div class="app-layout">
    <aside class="app-sidebar">
      <div>
        <div class="app-brand">
          <div class="app-brand__icon">✦</div>
          <div>
            <div class="app-brand__title">{{ meta?.app_name || 'Launchpad' }}</div>
            <div class="small faint">{{ meta?.environment || 'dev' }} · Vue</div>
          </div>
        </div>
        <nav class="app-nav">
          <button v-for="item in navItems" :key="item.key" class="app-nav__item" :class="{ 'app-nav__item--active': currentTab === item.key }" @click="currentTab = item.key">
            <span class="nav-icon">{{ item.icon }}</span><span class="grow">{{ item.label }}</span>
          </button>
          <a href="/api/docs" target="_blank" rel="noreferrer" class="app-nav__item"><span class="nav-icon">↗</span><span class="grow">FastAPI Docs</span></a>
        </nav>
      </div>
      <div class="app-sidebar__bottom">
        <div class="row between"><span class="muted">Backend</span><span class="badge" :class="healthy ? 'badge--ok' : 'badge--error'">{{ healthy === null ? 'Проверка…' : healthy ? 'Online' : 'Offline' }}</span></div>
        <div v-if="meta?.features.auth" class="auth-box">
          <template v-if="user"><span class="small">{{ user.name || user.email }}</span><button class="button button--ghost" @click="logout">Выйти</button></template>
          <button v-else class="button button--secondary full-width" @click="authOpen = true">Войти / регистрация</button>
        </div>
        <div class="small faint center">FastAPI · Vue 3 · TypeScript</div>
      </div>
    </aside>

    <main class="app-main">
      <template v-if="currentTab === 'example'">
        <header class="page-header">
          <div><p class="eyebrow">STARTER FEATURE</p><h1>Пример CRUD</h1><p class="muted">Переименуй или замени этот модуль под сущность своего проекта.</p></div>
          <button class="button button--primary" @click="openItem()">＋ Добавить запись</button>
        </header>
        <section class="stats-grid">
          <article class="panel stat"><span class="muted">Всего записей</span><strong>{{ total }}</strong></article>
          <article class="panel stat"><span class="muted">В работе</span><strong>{{ inProgress }}</strong></article>
          <article class="panel stat"><span class="muted">Завершено</span><strong>{{ done }}</strong></article>
        </section>
        <section class="panel filters">
          <input v-model="search" class="input" placeholder="Поиск по названию и описанию" />
          <select v-model="statusFilter" class="input select"><option value="all">Все статусы</option><option value="todo">В планах</option><option value="in_progress">В работе</option><option value="done">Готово</option></select>
        </section>
        <p v-if="itemError" class="error-message">{{ itemError }} <button class="button button--ghost" @click="loadItems">Повторить</button></p>
        <p v-else-if="itemBusy && !items.length" class="muted">Загрузка…</p>
        <div v-else-if="!items.length" class="panel empty"><h2>Пока нет записей</h2><p class="muted">Создай запись или замени эту демонстрационную сущность на свою.</p><button class="button button--primary" @click="openItem()">Добавить запись</button></div>
        <section v-else class="items-grid">
          <article v-for="item in items" :key="item.id" class="panel item-card">
            <div class="row between"><button class="status-pill" @click="cycleStatus(item)">{{ statusLabels[item.status] }} · сменить</button><span class="small faint">{{ new Date(item.created_at).toLocaleDateString() }}</span></div>
            <h2>{{ item.title }}</h2><p class="muted description">{{ item.description || 'Нет описания' }}</p>
            <div class="row between card-actions"><span class="small faint">#{{ item.id }}</span><span class="row"><button class="button button--ghost" @click="openItem(item)">Изменить</button><button class="button button--ghost danger" @click="deleteItem(item)">Удалить</button></span></div>
          </article>
        </section>
      </template>

      <template v-else-if="currentTab === 'ai'">
        <header class="page-header"><div><p class="eyebrow">OPTIONAL MODULE</p><h1>AI-пример</h1><p class="muted">Пример вызова OpenAI-compatible API через FastAPI.</p></div></header>
        <section class="panel chat-panel">
          <div class="chat-messages"><p v-if="!messages.length" class="muted">Напиши сообщение, чтобы проверить интеграцию.</p><div v-for="(message, index) in messages" :key="index" class="chat-message" :class="`chat-message--${message.role}`"><strong>{{ message.role === 'user' ? 'Ты' : 'AI' }}</strong><p>{{ message.content }}</p></div><p v-if="aiBusy" class="muted">Генерирую ответ…</p></div>
          <p v-if="aiError" class="error-message">{{ aiError }}</p>
          <form class="chat-form" @submit.prevent="sendPrompt"><input v-model="prompt" class="input" :disabled="aiBusy" placeholder="Сообщение…" /><button class="button button--primary" :disabled="aiBusy || !prompt.trim()">Отправить</button></form>
        </section>
      </template>

      <template v-else>
        <header class="page-header"><div><p class="eyebrow">OPTIONAL MODULE</p><h1>Загрузка файлов</h1><p class="muted">Демонстрация upload API и локального хранения.</p></div><button class="button button--primary" :disabled="uploadBusy" @click="fileInput?.click()">{{ uploadBusy ? 'Загружаю…' : 'Выбрать файл' }}</button></header>
        <input ref="fileInput" hidden type="file" @change="uploadFile(($event.target as HTMLInputElement).files?.[0])" />
        <div class="panel drop-zone" :class="{ 'drop-zone--active': dragOver }" @click="fileInput?.click()" @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="dragOver = false; uploadFile($event.dataTransfer?.files[0])">Перетащи файл сюда или нажми для выбора</div>
        <p v-if="uploadError" class="error-message">{{ uploadError }} <button class="button button--ghost" @click="loadFiles">Обновить</button></p>
        <section v-else class="items-grid"> <article v-for="file in files" :key="file.name" class="panel item-card"><h2>{{ file.name }}</h2><p class="muted">{{ file.content_type }} · {{ Math.ceil(file.size / 1024) }} КБ</p><a :href="file.url" target="_blank" rel="noreferrer">Открыть файл ↗</a></article><p v-if="!files.length" class="muted">Загруженных файлов пока нет.</p></section>
      </template>
    </main>

    <div v-if="itemModalOpen" class="overlay" @click.self="itemModalOpen = false">
      <form class="panel modal" @submit.prevent="saveItem"><div class="row between"><h2>{{ editing ? 'Изменить запись' : 'Новая запись' }}</h2><button type="button" class="button button--ghost" @click="itemModalOpen = false">✕</button></div>
        <label class="field">Название<input v-model="itemForm.title" class="input" required maxlength="160" /></label><label class="field">Описание<textarea v-model="itemForm.description" class="input textarea" rows="4"></textarea></label><label class="field">Статус<select v-model="itemForm.status" class="input select"><option value="todo">В планах</option><option value="in_progress">В работе</option><option value="done">Готово</option></select></label><p v-if="itemError" class="error-message">{{ itemError }}</p><div class="row end"><button type="button" class="button button--ghost" @click="itemModalOpen = false">Отмена</button><button class="button button--primary" :disabled="itemBusy">{{ itemBusy ? 'Сохраняю…' : 'Сохранить' }}</button></div>
      </form>
    </div>
    <div v-if="authOpen" class="overlay" @click.self="authOpen = false">
      <form class="panel modal" @submit.prevent="submitAuth"><div class="row between"><h2>{{ authMode === 'login' ? 'Вход' : 'Регистрация' }}</h2><button type="button" class="button button--ghost" @click="authOpen = false">✕</button></div><div class="row"><button type="button" class="button" @click="authMode = 'login'">Войти</button><button type="button" class="button" @click="authMode = 'register'">Регистрация</button></div><label v-if="authMode === 'register'" class="field">Имя<input v-model="authForm.name" class="input" /></label><label class="field">Email<input v-model="authForm.email" class="input" type="email" required /></label><label class="field">Пароль<input v-model="authForm.password" class="input" type="password" required /></label><p v-if="authError" class="error-message">{{ authError }}</p><button class="button button--primary full-width" :disabled="authBusy">{{ authBusy ? 'Подождите…' : authMode === 'login' ? 'Войти' : 'Создать аккаунт' }}</button></form>
    </div>
  </div>
</template>

<style>
#app { min-height: 100%; }
.app-layout { display:flex; min-height:100vh; }
.app-sidebar { width:var(--sidebar-w); flex-shrink:0; background:var(--bg-elevated); border-right:1px solid var(--border); display:flex; flex-direction:column; justify-content:space-between; padding:20px 16px; position:sticky; top:0; height:100vh; }
.app-brand { display:flex; align-items:center; gap:12px; padding:8px 10px; margin-bottom:20px; }
.app-brand__icon { width:36px; height:36px; border-radius:10px; background:var(--gradient); display:grid; place-items:center; color:white; box-shadow:var(--shadow-glow); }
.app-brand__title { font-weight:750; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.app-nav { display:flex; flex-direction:column; gap:4px; }
.app-nav__item { display:flex; align-items:center; gap:10px; width:100%; padding:10px 12px; border:0; border-radius:9px; color:var(--text-muted); background:transparent; text-align:left; font:inherit; cursor:pointer; }
.app-nav__item:hover,.app-nav__item--active { color:var(--text); background:var(--surface-hover); }
.app-sidebar__bottom { display:flex; flex-direction:column; gap:12px; }
.app-main { width: 100%; max-width: 1500px; margin: 0 auto; padding: 36px clamp(20px, 4vw, 56px); }
.page-header { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:26px; }
.page-header h1 { margin: 3px 0 8px; }
.eyebrow { color:var(--accent-2); font:600 .72rem var(--font-mono); letter-spacing:.12em; }
.muted { color:var(--text-muted); }
.faint { color:var(--text-faint); }
.small { font-size:.82rem; }
.center { text-align:center; }
.row { display:flex; align-items:center; gap:10px; }
.row.between { justify-content:space-between; }
.row.end { justify-content:flex-end; }
.grow { flex:1; }
.nav-icon { width:22px; text-align:center; font-size:1.1rem; }
.panel { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:18px; }
.button { border:1px solid var(--border); border-radius:9px; padding:9px 13px; color:var(--text); background:var(--surface-strong); font:inherit; cursor:pointer; }
.button:hover { background:var(--surface-hover); }
.button:disabled { opacity:.55; cursor:not-allowed; }
.button--primary { color:#fff; background:var(--accent); border-color:transparent; font-weight:600; }
.button--secondary { background:var(--surface-strong); }
.button--ghost { background:transparent; }
.danger,.error-message { color:var(--danger); }
.full-width { width:100%; }
.stats-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-bottom:18px; }
.stat { display:flex; flex-direction:column; gap:10px; }.stat strong { font-size:1.8rem; }
.filters { display:flex; gap:12px; margin-bottom:18px; }
.input { width:100%; min-width:0; border:1px solid var(--border-strong); border-radius:9px; padding:10px 12px; color:var(--text); background:var(--bg-elevated); font:inherit; }
.select { max-width:220px; }.items-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr)); gap:14px; }
.item-card { display:flex; flex-direction:column; gap:14px; }.item-card h2 { font-size:1.1rem; }.description { min-height:36px; white-space:pre-wrap; }.card-actions { border-top:1px solid var(--border); padding-top:12px; margin-top:auto; }
.status-pill,.badge { border:1px solid var(--border); border-radius:999px; padding:4px 9px; background:var(--surface-strong); color:var(--text); font:inherit; font-size:.78rem; }.status-pill { cursor:pointer; }.badge--ok { color:var(--success); }.badge--error { color:var(--danger); }
.empty { text-align:center; display:grid; justify-items:center; gap:12px; padding:48px 20px; }.error-message { margin:12px 0; }
.auth-box { margin:14px 0; }.auth-box:has(.small) { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.overlay { position:fixed; inset:0; z-index:20; display:grid; place-items:center; padding:20px; background:rgb(0 0 0 / .62); }.modal { width:min(100%,480px); display:flex; flex-direction:column; gap:16px; box-shadow:var(--shadow); }.field { display:grid; gap:6px; color:var(--text-muted); font-size:.9rem; }.textarea { resize:vertical; }
.chat-panel { padding:0; overflow:hidden; }.chat-messages { min-height:300px; max-height:55vh; overflow:auto; display:flex; flex-direction:column; gap:14px; padding:20px; }.chat-message { max-width:85%; padding:12px 14px; border-radius:12px; background:var(--surface-hover); }.chat-message--user { align-self:flex-end; background:var(--accent-soft); }.chat-message p { white-space:pre-wrap; margin-top:5px; }.chat-form { display:flex; gap:10px; border-top:1px solid var(--border); padding:14px; }.drop-zone { display:grid; place-items:center; min-height:160px; margin-bottom:18px; border-style:dashed; cursor:pointer; color:var(--text-muted); }.drop-zone--active { border-color:var(--accent); background:var(--surface-hover); }
@media(max-width:760px) { .app-layout { display:block; }.app-sidebar { position:static; height:auto; width:100%; gap:16px; }.app-sidebar__bottom { display:none; }.app-nav { flex-direction:row; overflow:auto; }.app-nav__item { white-space:nowrap; }.app-main { padding:24px 16px; }.page-header { align-items:flex-start; flex-direction:column; }.stats-grid { grid-template-columns:1fr; }.filters { flex-direction:column; }.select { max-width:none; } }
</style>
