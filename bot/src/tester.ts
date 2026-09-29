// 테스트용 플레이어(Claude, op): IN 파일에 줄 추가 → 채팅/명령 전송, 수신 채팅 출력
import mineflayer from 'mineflayer'
import { conn } from './cfg'
import { readFileSync, writeFileSync } from 'fs'
const IN = process.env.IN ?? '/tmp/cw/say.txt'
writeFileSync(IN, '')
const b = mineflayer.createBot(conn('Claude'))
const log = (...a: any[]) => console.log(new Date().toISOString().slice(11, 19), ...a)
let sent = 0
b.once('spawn', () => {
  log('SPAWN', b.entity.position)
  setInterval(() => {
    const ls = readFileSync(IN, 'utf8').split('\n').filter(Boolean)
    for (; sent < ls.length; sent++) { log('SEND', ls[sent]); ls[sent].startsWith('/') ? b.chat(ls[sent]) : b.chat(ls[sent]) }
  }, 500)
})
b.on('messagestr', m => log('MSG', m))
b.on('end', r => { log('END', r); process.exit(1) })
b.on('error', e => log('ERR', e))
