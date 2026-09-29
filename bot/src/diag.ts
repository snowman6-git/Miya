import mineflayer from 'mineflayer'
import { conn } from './cfg'
const b = mineflayer.createBot(conn('Diag'))
const inv = () => b.inventory.items().map(i => `${i.name}:${i.count}@${i.slot}`).join(' ')
b.once('spawn', async () => {
  await new Promise(r => setTimeout(r, 4000))
  console.log('start', inv())
  const mc = require('minecraft-data')(b.version)
  const rs = b.recipesFor(mc.itemsByName.oak_planks.id, null, 1, null)
  console.log('recipes', rs.length, rs[0] && JSON.stringify(rs[0].delta), rs[0]?.result)
  const t = Date.now()
  try { await b.craft(rs[0], 1, undefined); console.log('craft done', Date.now() - t) } catch (e: any) { console.log('craft err', e.message) }
  for (let i = 0; i < 30; i++) { console.log(i, inv(), 'cursor', (b.inventory as any).selectedItem?.name, 'grid', b.inventory.slots.slice(0, 5).map(x => x?.name + ':' + x?.count).join(',')); await new Promise(r => setTimeout(r, 500)) }
  b.quit(); process.exit(0)
})
