"""
SQL generation module for creating database statements from parsed loot data.
"""

from .config import QUALITY_LABELS, PROFESSION_SKILL_ID
from .enricher import decide_drop_chance
import random


class SQLGenerator:
    """Generates SQL blocks from NPC loot data."""

    @staticmethod
    def generate_loot_sql(npc_id, items, npc_name=None, reference=0, needsquest=0, lootmode=23, groupid=0, mincount=1, maxcount=1, shared=0):
        """
        Generate SQL REPLACE and conditions blocks for NPC loot.
        
        Args:
            npc_id: Numeric NPC ID
            items: List of enriched item dicts
            npc_name: Human-readable NPC name (uses ID if None)
            lootmode: Loot mode value for SQL (default 23 for Normal + RDF/LRF + heroic + mythic)
            groupid: Group ID for SQL (default 0)
            mincount: Min count value for SQL (default 1)
            maxcount: Max count value for SQL (default 1)
            shared: Shared value for SQL (default 0)
            
        Returns:
            String containing comment block and SQL statements
        """
        if not npc_name:
            npc_name = str(npc_id)

        comment_lines = [f"/* NPC {npc_id} - {npc_name} loot list"]

        r = random.random()

        if r < 0.15:
            comment_lines.append("Ddraigs sheep is moist.")
        elif r < 0.10:
            comment_lines.append("Shin is so fucking gay...")
        elif r < 0.05:
            for _ in range(5):
                comment_lines.append("Domestic violence is frowned upon.")

        vals = []
        skipped = []

        # Process each item
        for it in items:
            iid = it['id']
            chance = decide_drop_chance(it)

            if chance is None:
                skipped.append(iid)
                continue

            # Build comment for this item
            comment_parts = SQLGenerator._build_item_comment_parts(it, chance)
            comment = f"{iid}"

            if comment_parts:
                comment += " -- " + " -- ".join(comment_parts)
                thisComment = " ".join(comment_parts).split(":")[4]

            comment_lines.append(comment)

            # Format chance for SQL
            chance_sql = SQLGenerator._format_chance_for_sql(chance)
			
			# re-format from old style to newer TC for quest/chance
            if chance < 0:
                needsquest = 1
                chance = chance * -1

            # use per-item min/max if present (from parsed 'stack' values)
            minc, maxc = SQLGenerator._get_item_counts(it, mincount, maxcount)

            vals.append(f"(@NPC,{iid},{reference},{chance_sql},{needsquest},{lootmode},{groupid},{minc},{maxc},\"{thisComment}\",{shared})")

        comment_lines.append("*/\n")

        sql_lines = []
        sql_lines.append(f"SET @NPC := {npc_id};")
        sql_lines.append("REPLACE INTO creature_loot_template (`entry`,`item`,`reference`,`chance`,`needsquest`,`lootmode`,`groupid`,`mincount`,`maxcount`,`comment`,`shared`) VALUES")

        if skipped:
            print(f"[!] Skipping {len(skipped)} items with no NPC-provided drop chance: {skipped}")

        sql_lines.append(",\n".join(vals) + ";")

        # Generate loot conditions for recipe items
        condition_sql = SQLGenerator._generate_condition_sql(npc_id, items)

        if condition_sql:
            sql_lines.append(condition_sql)

        return "\n".join(comment_lines + sql_lines)

    @staticmethod
    def generate_gameobject_loot_sql(obj_id, items, obj_name=None, reference=0, needsquest=0, lootmode=23, groupid=0, mincount=1, maxcount=1):
        """
        Generate SQL for gameobject loot tables. Uses gameobject_loot_template 
        table and @GOB variable. Conditions use SourceType 4.
        """
        if not obj_name:
            obj_name = str(obj_id)

        comment_lines = [f"/* GameObject {obj_id} - {obj_name} loot list"]
        r = random.random()

        if r < 0.15:
            comment_lines.append("Ddraigs sheep is moist.")
        elif r < 0.10:
            comment_lines.append("Shin is so fucking gay...")
        elif r < 0.05:
            for _ in range(5):
                comment_lines.append("Domestic violence is frowned upon.")
        vals = []
        skipped = []

        for it in items:
            iid = it['id']
            chance = decide_drop_chance(it)

            if chance is None:
                skipped.append(iid)
                continue

            comment_parts = SQLGenerator._build_item_comment_parts(it, chance)
            comment = f"{iid}"

            if comment_parts:
                comment += " -- " + " -- ".join(comment_parts)
                thisComment = " ".join(comment_parts).split(":")[4]

            comment_lines.append(comment)

            chance_sql = SQLGenerator._format_chance_for_sql(chance)
            minc, maxc = SQLGenerator._get_item_counts(it, mincount, maxcount)
            
            # re-format from old style to newer TC for quest/chance
            if chance < 0:
                needsquest = 1
                chance = chance * -1

            vals.append(f"(@GOB,{iid},{reference},{chance_sql},{needsquest},{lootmode},{groupid},{minc},{maxc},\"{thisComment}\")")

        comment_lines.append("*/\n")

        sql_lines = []
        sql_lines.append(f"SET @GOB := {obj_id};")
        sql_lines.append("REPLACE INTO gameobject_loot_template (`entry`,`item`,`reference`,`chance`,`needsquest`,`lootmode`,`groupid`,`mincount`,`maxcount`,`comment`) VALUES")

        if skipped:
            print(f"[!] Skipping {len(skipped)} items with no GameObject-provided drop chance: {skipped}")

        sql_lines.append(",\n".join(vals) + ";")

        condition_sql = SQLGenerator._generate_condition_sql_for_gameobject(obj_id, items)

        if condition_sql:
            sql_lines.append(condition_sql)

        return "\n".join(comment_lines + sql_lines)

    @staticmethod
    def generate_item_loot_sql(item_id, items, item_name=None, reference=0, needsquest=0, lootmode=23, groupid=0, mincount=1, maxcount=1):
        """
        Generate SQL for item/container loot tables. Uses @ITEM variable and
        writes to `item_loot_template`. Conditions use SourceType 5.
        """
        if not item_name:
            item_name = str(item_id)

        comment_lines = [f"/* Item {item_id} - {item_name} contains list"]
        r = random.random()

        if r < 0.15:
            comment_lines.append("Ddraigs sheep is moist.")
        elif r < 0.10:
            comment_lines.append("Shin is so fucking gay...")
        elif r < 0.05:
            for _ in range(5):
                comment_lines.append("Domestic violence is frowned upon.")
        vals = []
        skipped = []

        for it in items:
            iid = it['id']
            chance = decide_drop_chance(it)

            if chance is None:
                skipped.append(iid)
                continue

            comment_parts = SQLGenerator._build_item_comment_parts(it, chance)
            comment = f"{iid}"

            if comment_parts:
                comment += " -- " + " -- ".join(comment_parts)
                thisComment = " ".join(comment_parts).split(":")[4]

            comment_lines.append(comment)

            chance_sql = SQLGenerator._format_chance_for_sql(chance)
            minc, maxc = SQLGenerator._get_item_counts(it, mincount, maxcount)
            
            # re-format from old style to newer TC for quest/chance
            if chance < 0:
                needsquest = 1
                chance = chance * -1

            vals.append(f"(@ITEM,{iid},{reference},{chance_sql},{needsquest},{lootmode},{groupid},{minc},{maxc},\"{thisComment}\")")

        comment_lines.append("*/\n")

        sql_lines = []
        sql_lines.append(f"SET @ITEM := {item_id};")
        sql_lines.append("REPLACE INTO item_loot_template (`entry`,`item`,`reference`,`chance`,`needsquest`,`lootmode`,`groupid`,`mincount`,`maxcount`,`comment`) VALUES")

        if skipped:
            print(f"[!] Skipping {len(skipped)} items with no Item-provided drop chance: {skipped}")

        sql_lines.append(",\n".join(vals) + ";")

        condition_sql = SQLGenerator._generate_condition_sql_for_item(item_id, items)

        if condition_sql:
            sql_lines.append(condition_sql)

        return "\n".join(comment_lines + sql_lines)

    @staticmethod
    def generate_zone_loot_sql(zone_id, items, zone_name=None, reference=0, needsquest=0, lootmode=1, groupid=0, mincount=1, maxcount=1):
        """
        Generate SQL for fishing loot tables. Uses fishing_loot_template 
        table and @ZONE variable. Conditions use SourceType 3.
        """
        if not zone_name:
            zone_name = str(zone_id)

        comment_lines = [f"/* Zone {zone_id} - {zone_name} loot list"]
        r = random.random()

        if r < 0.15:
            comment_lines.append("Ddraigs sheep is moist.")
        elif r < 0.10:
            comment_lines.append("Shin is so fucking gay...")
        elif r < 0.05:
            for _ in range(5):
                comment_lines.append("Domestic violence is frowned upon.")
        vals = []
        skipped = []

        for it in items:
            iid = it['id']
            chance = decide_drop_chance(it)
            print(f"chance for item {iid} is {chance}\n")
            if chance is None:
                skipped.append(iid)
                continue

            comment_parts = SQLGenerator._build_item_comment_parts(it, chance)
            comment = f"{iid}"

            if comment_parts:
                comment += " -- " + " -- ".join(comment_parts)
                thisComment = " ".join(comment_parts).split(":")[4]

            comment_lines.append(comment)

            chance_sql = SQLGenerator._format_chance_for_sql(chance)
            minc, maxc = SQLGenerator._get_item_counts(it, mincount, maxcount)
            
            # re-format from old style to newer TC for quest/chance
            if chance < 0:
                needsquest = 1
                chance = chance * -1

            vals.append(f"(@ZONE,{iid},{reference},{chance_sql},{needsquest},{lootmode},{groupid},{minc},{maxc},\"{thisComment}\")")

        comment_lines.append("*/\n")

        sql_lines = []
        sql_lines.append(f"SET @ZONE := {zone_id};")
        sql_lines.append("REPLACE INTO fishing_loot_template (`entry`,`item`,`reference`,`chance`,`needsquest`,`lootmode`,`groupid`,`mincount`,`maxcount`,`comment`) VALUES")

        if skipped:
            print(f"[!] Skipping {len(skipped)} items with no zone-provided drop chance: {skipped}")

        sql_lines.append(",\n".join(vals) + ";")

        condition_sql = SQLGenerator._generate_condition_sql_for_fishing(zone_id, items)

        if condition_sql:
            sql_lines.append(condition_sql)

        return "\n".join(comment_lines + sql_lines)

    @staticmethod
    def _generate_condition_sql_for_item(item_id, items):
        """
        Generate conditions for item-contained recipe drops. Uses SourceTypeOrReferenceId=5
        and the @ITEM variable as SourceGroup.
        """
        recipe_items = [
            it for it in items
            if it.get('is_recipe') and it.get('profession') and it.get('id')
        ]

        recipe_with_spell = [
            (it['id'], it['profession'])
            for it in recipe_items
            if PROFESSION_SKILL_ID.get(it['profession'])
        ]

        if not recipe_with_spell:
            return ""

        sql_lines = []
        ids = ",".join(str(i) for i, _ in recipe_with_spell)

        sql_lines.append("\n-- loot conditions")
        sql_lines.append(
            f"DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=5\n"
            f"    AND `SourceGroup`=@ITEM\n"
            f"    AND `SourceEntry` IN ({ids}); -- item IDs"
        )

        sql_lines.append(
            "INSERT INTO conditions (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, "
            "`SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, "
            "`ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, "
            "`ErrorTextId`, `ScriptName`, `Comment`) VALUES"
        )

        cond_vals = []

        for iid, prof in recipe_with_spell:
            spell = PROFESSION_SKILL_ID.get(prof)

            cond_vals.append(
                f"(5, @ITEM, {iid}, 0, 1, 7, 0, {spell}, 1, 0, 0, 0, '', 'Item Container - Has {prof.capitalize()}')"
            )

            cond_vals.append(
                f"(5, @ITEM, {iid}, 0, 1, 2, 0, {iid}, 1, 1, 1, 0, '', 'Item Container - No Item')"
            )

        sql_lines.append(",\n".join(cond_vals) + ";")

        return "\n".join(sql_lines)

    @staticmethod
    def _generate_condition_sql_for_gameobject(obj_id, items):
        """
        Generate conditions for gameobject recipe drops. Uses SourceTypeOrReferenceId=4
        and the @GOB variable.
        """
        recipe_items = [
            it for it in items
            if it.get('is_recipe') and it.get('profession') and it.get('id')
        ]

        recipe_with_spell = [
            (it['id'], it['profession'])
            for it in recipe_items
            if PROFESSION_SKILL_ID.get(it['profession'])
        ]

        if not recipe_with_spell:
            return ""

        sql_lines = []
        ids = ",".join(str(i) for i, _ in recipe_with_spell)

        sql_lines.append("\n-- loot conditions")
        sql_lines.append(
            f"DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=4\n"
            f"    AND `SourceGroup`=@GOB\n"
            f"    AND `SourceEntry` IN ({ids}); -- item IDs"
        )

        sql_lines.append(
            "INSERT INTO conditions (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, "
            "`SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, "
            "`ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, "
            "`ErrorTextId`, `ScriptName`, `Comment`) VALUES"
        )

        cond_vals = []

        for iid, prof in recipe_with_spell:
            spell = PROFESSION_SKILL_ID.get(prof)

            cond_vals.append(
                f"(4, @GOB, {iid}, 0, 1, 7, 0, {spell}, 1, 0, 0, 0, '', 'Item Drop - Has {prof.capitalize()}')"
            )

            cond_vals.append(
                f"(4, @GOB, {iid}, 0, 1, 2, 0, {iid}, 1, 1, 1, 0, '', 'Item Drop - No Item')"
            )

        sql_lines.append(",\n".join(cond_vals) + ";")

        return "\n".join(sql_lines)

    @staticmethod
    def _generate_condition_sql_for_fishing(zone_id, items):
        """
        Generate conditions for fishing recipe drops. Uses SourceTypeOrReferenceId=3
        and the @ZONE variable.
        """
        recipe_items = [
            it for it in items
            if it.get('is_recipe') and it.get('profession') and it.get('id')
        ]

        recipe_with_spell = [
            (it['id'], it['profession'])
            for it in recipe_items
            if PROFESSION_SKILL_ID.get(it['profession'])
        ]

        if not recipe_with_spell:
            return ""

        sql_lines = []
        ids = ",".join(str(i) for i, _ in recipe_with_spell)

        sql_lines.append("\n-- loot conditions")
        sql_lines.append(
            f"DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=3\n"
            f"    AND `SourceGroup`=@ZONE\n"
            f"    AND `SourceEntry` IN ({ids}); -- item IDs"
        )

        sql_lines.append(
            "INSERT INTO conditions (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, "
            "`SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, "
            "`ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, "
            "`ErrorTextId`, `ScriptName`, `Comment`) VALUES"
        )

        cond_vals = []

        for iid, prof in recipe_with_spell:
            spell = PROFESSION_SKILL_ID.get(prof)

            cond_vals.append(
                f"(3, @ZONE, {iid}, 0, 1, 7, 0, {spell}, 1, 0, 0, 0, '', 'Item Drop - Has {prof.capitalize()}')"
            )

            cond_vals.append(
                f"(3, @ZONE, {iid}, 0, 1, 2, 0, {iid}, 1, 1, 1, 0, '', 'Item Drop - No Item')"
            )

        sql_lines.append(",\n".join(cond_vals) + ";")

        return "\n".join(sql_lines)


    @staticmethod
    def _build_item_comment_parts(item, chance):
        """
        Build comment parts for a single item.
        
        Args:
            item: Item dict
            chance: Computed drop chance
            
        Returns:
            List of comment strings
        """
        parts = []

        # Include computed NPC drop chance
        try:
            fval = float(chance)

            if abs(fval - round(fval)) < 1e-9:
                parts.append(f"chance:{int(round(fval))}%")
            else:
                parts.append(f"chance:{round(fval, 2)}%")
        except (ValueError, TypeError):
            pass

        # Mark quest items
        if item.get('is_quest'):
            parts.append('quest')

        # Quality label
        q = int(item.get('quality', 0) or 0)
        qlabel = QUALITY_LABELS.get(q, f'q{q}')

        parts.append(f"quality:{qlabel}")

        # Include stack / count range when available
        try:
            mn = item.get('min_count')
            mx = item.get('max_count')

            if mn is not None and mx is not None:
                parts.append(f"count:{int(mn)}-{int(mx)}")
        except Exception:
            pass

        # Recipe / profession
        if item.get('is_recipe'):
            prof = item.get('profession') or 'unknown'
            
            parts.append(f"{prof} (recipe)")

        # Item name
        parts.append(f"name:{item.get('name')}")

        return parts

    @staticmethod
    def _format_chance_for_sql(chance):
        """
        Format drop chance for SQL: integer if whole number, else up to 2 decimals.
        
        Args:
            chance: Float chance value
            
        Returns:
            String formatted for SQL
        """
        if abs(chance - round(chance)) < 1e-9:
            return str(int(round(chance)))
        else:
            return ('{:.2f}'.format(chance)).rstrip('0').rstrip('.')

    @staticmethod
    def _get_item_counts(item, default_min, default_max):
        """
        Safely retrieve integer min/max counts for an item, falling back to
        provided defaults when values are missing or invalid.

        Returns a tuple (minc, maxc).
        """
        try:
            minc = int(item.get('min_count')) if item.get('min_count') is not None else int(default_min)
        except Exception:
            minc = int(default_min)

        try:
            maxc = int(item.get('max_count')) if item.get('max_count') is not None else int(default_max)
        except Exception:
            maxc = int(default_max)

        return minc, maxc

    @staticmethod
    def _generate_condition_sql(npc_id, items):
        """
        Generate SQL conditions for profession recipes.
        
        Creates DELETE and INSERT statements for profession requirement conditions.
        
        Args:
            npc_id: Numeric NPC ID
            items: List of enriched item dicts
            
        Returns:
            SQL string or empty string if no conditions needed
        """
        # Find recipe items with profession
        recipe_items = [
            it for it in items
            if it.get('is_recipe') and it.get('profession') and it.get('id')
        ]

        # Filter to those with known profession skill IDs
        recipe_with_spell = [
            (it['id'], it['profession'])
            for it in recipe_items
            if PROFESSION_SKILL_ID.get(it['profession'])
        ]

        if not recipe_with_spell:
            return ""

        sql_lines = []
        ids = ",".join(str(i) for i, _ in recipe_with_spell)
        
        sql_lines.append("\n-- loot conditions")
        sql_lines.append(
            f"DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=1\n"
            f"    AND `SourceGroup`=@NPC\n"
            f"    AND `SourceEntry` IN ({ids}); -- item IDs"
        )
        sql_lines.append(
            "INSERT INTO conditions (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, "
            "`SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, "
            "`ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, "
            "`ErrorTextId`, `ScriptName`, `Comment`) VALUES"
        )

        cond_vals = []
        
        for iid, prof in recipe_with_spell:
            spell = PROFESSION_SKILL_ID.get(prof)

            # Has profession condition (ConditionType 7 using profession spell id)
            cond_vals.append(
                f"(1, @NPC, {iid}, 0, 1, 7, 0, {spell}, 1, 0, 0, 0, '', "
                f"'Item Drop - Has {prof.capitalize()}')"
            )

            # No-item fallback condition (ConditionType 2 pointing at item)
            cond_vals.append(
                f"(1, @NPC, {iid}, 0, 1, 2, 0, {iid}, 1, 1, 1, 0, '', "
                f"'Item Drop - No Item')"
            )

        sql_lines.append(",\n".join(cond_vals) + ";")

        return "\n".join(sql_lines)
